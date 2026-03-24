"""LLM client wrapper with retry, fallback models, and error recovery."""
from __future__ import annotations

import os
import json
import asyncio
import time
from typing import Optional, List, Dict, Callable
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

_client = None

# ── Token/Cost Tracking ─────────────────────────────────────────────
# Approximate costs per 1M tokens (input/output) for common models
MODEL_COSTS = {
    "gpt-4.1-nano":  {"input": 0.10, "output": 0.40},
    "gpt-4.1-mini":  {"input": 0.40, "output": 1.60},
    "gpt-4.1":       {"input": 2.00, "output": 8.00},
    "gpt-4o":        {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":   {"input": 0.15, "output": 0.60},
}

class UsageTracker:
    """Track token usage and estimated costs across all LLM calls."""
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0
        self.estimated_cost_usd = 0.0
        self._by_model = {}  # model -> {input, output, calls, cost}

    def record(self, model: str, input_tokens: int, output_tokens: int):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_calls += 1

        costs = MODEL_COSTS.get(model, {"input": 1.0, "output": 4.0})
        call_cost = (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000
        self.estimated_cost_usd += call_cost

        if model not in self._by_model:
            self._by_model[model] = {"input": 0, "output": 0, "calls": 0, "cost": 0.0}
        self._by_model[model]["input"] += input_tokens
        self._by_model[model]["output"] += output_tokens
        self._by_model[model]["calls"] += 1
        self._by_model[model]["cost"] += call_cost

    def summary(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "by_model": self._by_model,
        }

usage = UsageTracker()

# ── Fallback Chain ───────────────────────────────────────────────────
# If the primary model fails, try these in order
FALLBACK_CHAINS = {
    "gpt-4.1-nano": ["gpt-4.1-mini", "gpt-4.1-nano"],
    "gpt-4.1-mini": ["gpt-4.1-nano", "gpt-4.1-mini"],
    "gpt-4.1":      ["gpt-4.1-mini", "gpt-4.1-nano"],
    "gpt-4o":       ["gpt-4o-mini", "gpt-4.1-mini"],
}


def get_client():
    global _client
    if _client is None:
        from .config import Config
        cfg = Config()
        _client = AsyncOpenAI(api_key=cfg.openai_key, base_url=cfg.base_url)
    return _client


async def chat(
    messages: List[Dict],
    model: str = "gpt-4.1-nano",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    tools: Optional[List[Dict]] = None,
    retries: int = 3,
    fallback: bool = True,
) -> dict:
    """Send a chat completion request with retry and fallback logic.

    Retry strategy:
    1. Retry the same model up to `retries` times with exponential backoff
    2. If all retries fail and `fallback=True`, try fallback models
    3. If everything fails, raise the last exception
    """
    client = get_client()
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    last_error = None

    # Try primary model with retries
    for attempt in range(retries):
        try:
            response = await client.chat.completions.create(**kwargs)
            # Track token usage
            if hasattr(response, 'usage') and response.usage:
                usage.record(model, response.usage.prompt_tokens or 0, response.usage.completion_tokens or 0)
            return response.choices[0].message
        except Exception as e:
            last_error = e
            wait = min(2 ** attempt, 10)  # 1s, 2s, 4s... cap at 10s
            print(f"[LLM] {model} attempt {attempt+1}/{retries} failed: {e}. Retrying in {wait}s...")
            await asyncio.sleep(wait)

    # Try fallback models
    if fallback:
        fallbacks = FALLBACK_CHAINS.get(model, [])
        for fb_model in fallbacks:
            if fb_model == model:
                continue
            print(f"[LLM] Falling back to {fb_model}...")
            try:
                kwargs["model"] = fb_model
                response = await client.chat.completions.create(**kwargs)
                if hasattr(response, 'usage') and response.usage:
                    usage.record(fb_model, response.usage.prompt_tokens or 0, response.usage.completion_tokens or 0)
                print(f"[LLM] Fallback to {fb_model} succeeded")
                return response.choices[0].message
            except Exception as e:
                print(f"[LLM] Fallback {fb_model} also failed: {e}")
                last_error = e

    raise last_error


async def quick_chat(
    messages: List[Dict],
    model: str = "gpt-4.1-nano",
    max_tokens: int = 100,
) -> str:
    """Single-turn LLM call that returns just the text. No tools, no retries beyond default."""
    result = await chat(messages=messages, model=model, max_tokens=max_tokens, retries=1, fallback=True)
    return result.content or ""


async def chat_with_tools(
    messages: List[Dict],
    tool_defs: List[Dict],
    tool_handlers: Dict,
    model: str = "gpt-4.1-nano",
    max_rounds: int = 4,
    on_tool_call: Optional[object] = None,
    check_interrupt: Optional[Callable] = None,
) -> str:
    """Run a tool-use loop until the model produces a final text response.

    Features:
    - Automatic retry + fallback on LLM errors
    - Tool error recovery: if a tool fails, the error is sent back to the model
      so it can adapt (try different args, use a different tool, etc.)
    - Optional callback on each tool call for progress tracking

    Args:
        messages: conversation history
        tool_defs: OpenAI-format tool definitions
        tool_handlers: dict mapping function names to async callables
        model: model to use
        max_rounds: max tool-call rounds before forcing a text response
        on_tool_call: optional async callback(tool_name, args, result) for progress

    Returns:
        The final text response from the model.
    """
    msgs = list(messages)
    consecutive_errors = 0
    max_consecutive_errors = 3

    for round_num in range(max_rounds):
        if check_interrupt:
            override = check_interrupt()
            if override:
                msgs.append({"role": "user", "content": f"[SYSTEM EXPLICIT OVERRIDE/STEERING]: {override}"})
                
        try:
            response = await chat(msgs, model=model, tools=tool_defs if tool_defs else None)
        except Exception as e:
            # If even retry+fallback fails, inject error context and ask model to finish
            msgs.append({
                "role": "user",
                "content": f"The AI service encountered an error: {e}. Please provide your best answer based on the information gathered so far.",
            })
            try:
                response = await chat(msgs, model=model, tools=None, retries=1, fallback=True)
                return response.content or f"[System error during processing: {e}]"
            except Exception:
                return f"[System error: all LLM calls failed. Last error: {e}]"

        # If no tool calls, we're done
        if not response.tool_calls:
            return response.content or ""

        # Process tool calls
        msgs.append(response)
        round_had_error = False

        for tc in response.tool_calls:
            fn_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            handler = tool_handlers.get(fn_name)
            if handler:
                try:
                    result = await handler(**args)
                    result_str = json.dumps(result) if not isinstance(result, str) else result
                except Exception as e:
                    result_str = f"Tool error: {e}. Try a different approach or different arguments."
                    round_had_error = True
            else:
                result_str = f"Error: unknown tool '{fn_name}'. Available tools: {list(tool_handlers.keys())}"
                round_had_error = True

            # Progress callback
            if on_tool_call and asyncio.iscoroutinefunction(on_tool_call):
                try:
                    await on_tool_call(fn_name, args, result_str[:200])
                except Exception:
                    pass

            msgs.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str[:8000],
            })

        # Track consecutive error rounds for circuit breaking
        if round_had_error:
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                msgs.append({
                    "role": "user",
                    "content": "Multiple tool calls have failed. Please provide your best answer with the information you have so far, without using more tools.",
                })
                try:
                    response = await chat(msgs, model=model, tools=None)
                    return response.content or ""
                except Exception:
                    return "[Error: unable to complete task after multiple tool failures]"
        else:
            consecutive_errors = 0

    # If we exhausted rounds, ask for a summary
    msgs.append({"role": "user", "content": "Please provide your final answer now based on everything above."})
    response = await chat(msgs, model=model, tools=None)
    return response.content or ""
