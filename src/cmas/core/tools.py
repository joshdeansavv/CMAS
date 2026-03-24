"""Tool implementations for agents."""
from __future__ import annotations

import os
import json
import subprocess
import aiohttp
from pathlib import Path
from dotenv import load_dotenv

from ..frameworks import (
    select_and_apply as _fw_select_and_apply,
    apply_framework as _fw_apply,
    list_frameworks as _fw_list,
)

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


# ── Web Search (Tavily) ─────────────────────────────────────────────

async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using Tavily API."""
    if not TAVILY_API_KEY:
        return "Error: TAVILY_API_KEY not set"

    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "include_answer": True,
            },
        )
        data = await resp.json()

    answer = data.get("answer", "")
    results = []
    for r in data.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", "")[:500],
        })

    return json.dumps({"answer": answer, "results": results}, indent=2)


# ── File Operations ──────────────────────────────────────────────────

async def write_file(path: str, content: str) -> str:
    """Write content to a file within the project directory."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Wrote {len(content)} chars to {path}"


async def read_file(path: str) -> str:
    """Read content from a file."""
    p = Path(path)
    if not p.exists():
        return f"Error: {path} does not exist"
    content = p.read_text()
    if len(content) > 10000:
        return content[:10000] + f"\n... (truncated, {len(content)} total chars)"
    return content


async def list_files(directory: str) -> str:
    """List files in a directory."""
    p = Path(directory)
    if not p.exists():
        return f"Error: {directory} does not exist"
    files = [str(f.relative_to(p)) for f in p.rglob("*") if f.is_file()]
    return json.dumps(files[:100])


# ── Shell Command ────────────────────────────────────────────────────

async def run_command(command: str, timeout: int = 30) -> str:
    """Run a shell command and return output. Use cautiously."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        if len(output) > 5000:
            output = output[:5000] + "\n... (truncated)"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


# ── Python Execution ─────────────────────────────────────────────────

async def run_python(code: str) -> str:
    """Execute Python code and return output."""
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        if len(output) > 5000:
            output = output[:5000] + "\n... (truncated)"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: execution timed out after 60s"
    except Exception as e:
        return f"Error: {e}"


# ── Frameworks ───────────────────────────────────────────────────────

async def apply_framework(
    context: str,
    framework_id: str = "",
    component: str = "",
) -> str:
    """Apply an evidence-based coaching/transformation framework.

    If framework_id is empty, auto-detects the best framework from context.
    """
    if framework_id:
        return _fw_apply(framework_id, context, component)
    return _fw_select_and_apply(context)


async def list_available_frameworks() -> str:
    """List all available frameworks."""
    return json.dumps(_fw_list(), indent=2)


# ── Tool Registry ────────────────────────────────────────────────────

# OpenAI function-calling format definitions
TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information on any topic. Returns relevant results with snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "max_results": {"type": "integer", "description": "Max results (default 5)", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates directories as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write to"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read content from a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files in a directory recursively.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory to list"},
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute Python code and return the output. Use for data analysis, calculations, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a message to another agent or the orchestrator. Use to share findings, request data, or coordinate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Name of the recipient agent (e.g. 'ResearchAgent', 'orchestrator'), or 'SwarmChannel' to broadcast a blocker so idle specialists can help you."},
                    "content": {"type": "string", "description": "Message content"},
                },
                "required": ["recipient", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run secure shell commands natively. Use this to `pip install` required science packages, stand up local databases, spin up Docker containers, or orchestrate files before running python scripts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash/shell command to execute (e.g., 'pip install numpy' or 'mkdir data')"},
                    "timeout": {"type": "integer", "description": "Optional timeout in seconds (default 30)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "Dynamically spawn a specialized sub-agent to handle a complex task. This is NON-BLOCKING; it will spawn the agent in the background (Swarm style) and immediately return control to you so you can spawn more agents or continue thinking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": {"type": "string", "description": "The specific domain expertise needed (e.g., 'quantum physics', 'code reviewer', 'web scraping')"},
                    "task": {"type": "string", "description": "Clear and detailed description of the task for the specialist"},
                },
                "required": ["specialty", "task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_framework",
            "description": (
                "Apply an evidence-based coaching or transformation framework to the current situation. "
                "Auto-detects the best framework if none specified. Available frameworks: "
                "CBT (cognitive distortions, Socratic questioning), ACT (acceptance, values-based action), "
                "DBT (distress tolerance, emotional regulation, DEAR MAN communication), "
                "Stages of Change (readiness assessment), Goal Setting (SMART, HARD, GROW, OKR), "
                "Strategic (SWOT, Eisenhower Matrix, 80/20 Pareto, 7 Habits), "
                "Behavioral (Habit Loop, Fogg Model, Four Tendencies), "
                "Financial (Wealth Pyramid, Profit First, Cashflow Quadrant), "
                "Conflict (Drama Triangle, Internal Family Systems), "
                "NLP (reframing, meta model, outcome specification). "
                "Use this when the task involves personal development, goal setting, behavioral change, "
                "strategic decisions, conflict resolution, or overcoming mental blocks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "Description of the current situation, problem, or goal the framework should address"
                    },
                    "framework_id": {
                        "type": "string",
                        "description": "Optional: specific framework ID (cbt, act, dbt, stages_of_change, goal_setting, strategic, behavioral, financial, conflict, nlp). Leave empty for auto-detection.",
                        "enum": ["", "cbt", "act", "dbt", "stages_of_change", "goal_setting", "strategic", "behavioral", "financial", "conflict", "nlp"]
                    },
                    "component": {
                        "type": "string",
                        "description": "Optional: specific component within the framework (e.g., 'socratic_questions', 'smart', 'eisenhower', 'habit_loop', 'dear_man', 'drama_triangle')"
                    },
                },
                "required": ["context"],
            },
        },
    },
]

# Map function names to handlers
TOOL_HANDLERS = {
    "web_search": web_search,
    "write_file": write_file,
    "read_file": read_file,
    "list_files": list_files,
    "run_python": run_python,
    "run_command": run_command,
    "apply_framework": apply_framework,
}
