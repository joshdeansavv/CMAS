"""Base agent with reasoning, memory, and gateway routing."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable

from .llm import chat_with_tools
from .tools import TOOL_DEFS
from .state import Hub, Task, TaskStatus
from .memory import Memory
from .reasoning import Reasoner


def _fmt_progress(agent_name: str, tool_name: str, args: dict) -> str:
    """Format a tool call into a human-readable progress message."""
    q = args.get('query', '')
    if tool_name == 'web_search':
        return f"{agent_name} searching: \"{q[:70]}\""
    if tool_name == 'delegate_task':
        sp = args.get('specialty', 'specialist')
        t  = args.get('task', '')[:60]
        return f"{agent_name} deploying {sp} agent: \"{t}\""
    if tool_name == 'send_message':
        to  = args.get('recipient', 'agent')
        msg = args.get('content', '')[:70]
        return f"{agent_name} → {to}: {msg}"
    if tool_name == 'write_file':
        from pathlib import Path as _P
        return f"{agent_name} writing: {_P(args.get('path', 'file')).name}"
    if tool_name == 'run_python':
        first_line = args.get('code', '').strip().split('\n')[0][:50]
        return f"{agent_name} running Python: {first_line}"
    if tool_name == 'run_command':
        return f"{agent_name} running: {args.get('command', '')[:60]}"
    return f"{agent_name} using {tool_name}"


class Agent:
    """An autonomous agent that REASONS, then acts, then reflects.

    Cognitive loop per task:
    1. REASON — analyze the task, generate hypotheses, plan approach
    2. ACT — use tools (web search, file ops, code) guided by the plan
    3. REFLECT — assess what was accomplished, store insights in memory

    All tool calls routed through Gateway for access control + auditing.
    """

    def __init__(
        self,
        name: str,
        role: str,
        hub: Hub,
        workspace: Path,
        model: str = "gpt-4.1-nano",
        gateway: Any = None,
        memory: Optional[Memory] = None,
        depth: int = 0,
        progress_callback: Optional[Callable] = None,
    ):
        self.name = name
        self.role = role
        self.hub = hub
        self.workspace = workspace
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.gateway = gateway
        self.memory = memory
        self.depth = depth
        self.progress_callback = progress_callback
        self.reasoner = Reasoner(model=model)
        self._log_lines: List[str] = []
        # Persistent conversation history — survives across multiple executions
        # so follow-up tasks retain context from prior work.
        self._conversation_history: List[Dict] = []
        self._tasks_completed: List[str] = []

    def _get_memory_context(self, task_description: str) -> str:
        """Search persistent memory for relevant prior knowledge."""
        if not self.memory:
            return ""

        words = task_description.split()
        search_terms = [w for w in words if len(w) > 4][:5]
        query = " ".join(search_terms) if search_terms else task_description[:50]

        entries = self.memory.search(query, limit=5)
        if not entries:
            return ""

        lessons = self.memory.get_lessons(applies_to=query, limit=3)

        context = self.memory.format_for_context(entries, max_chars=2000)
        if lessons:
            context += "\n\nLESSONS FROM PAST EXPERIENCE:"
            for l in lessons:
                context += f"\n  What happened: {l['what_happened'][:100]}"
                context += f"\n  Lesson: {l['what_learned'][:100]}\n"

        return context

    async def _reason_about_task(self, task_description: str) -> str:
        """Phase 1: REASON — think before acting.

        Uses the reasoning engine to:
        - Understand what's really being asked
        - Identify key unknowns
        - Plan an approach
        - Generate hypotheses if applicable
        """
        self._log("Reasoning about task...")

        # Chain-of-thought analysis
        reasoning = await self.reasoner.think_step_by_step(
            problem=task_description,
            context=self._get_memory_context(task_description),
        )

        # Build reasoning context for the agent
        lines = ["REASONING (think before you act):"]
        lines.append(f"  Understanding: {reasoning.get('understanding', 'N/A')}")

        assumptions = reasoning.get("assumptions", [])
        if assumptions:
            lines.append(f"  Assumptions: {'; '.join(str(a) for a in assumptions[:3])}")

        steps = reasoning.get("steps", [])
        if steps:
            lines.append("  Planned steps:")
            for s in steps[:5]:
                lines.append(f"    {s.get('step', '?')}. {s.get('reasoning', 'N/A')}")

        insight = reasoning.get("key_insight", "")
        if insight:
            lines.append(f"  Key insight: {insight}")

        unknowns = reasoning.get("unknowns", [])
        if unknowns:
            lines.append(f"  Must find out: {'; '.join(str(u) for u in unknowns[:3])}")

        confidence = reasoning.get("confidence", 0.5)
        lines.append(f"  Confidence: {confidence:.0%}")

        self._log(f"Reasoning complete (confidence: {confidence:.0%})")
        return "\n".join(lines)

    def _system_prompt(self, task_description: str, reasoning_context: str) -> str:
        memory_context = self._get_memory_context(task_description)
        memory_section = f"\n\nPRIOR KNOWLEDGE:\n{memory_context}" if memory_context else ""

        return f"""You are {self.name}, a specialized AI agent in a multi-agent system.

YOUR ROLE: {self.role}

YOUR CURRENT TASK: {task_description}

{reasoning_context}

YOUR WORKSPACE: {self.workspace}
Save any outputs (research findings, analysis, data files) to your workspace directory.

INTER-AGENT COMMUNICATION:
- Use send_message to share findings with other agents or the orchestrator.
- You can send to: "orchestrator", "ResearchAgent", "AnalystAgent", "WriterAgent", or any specialist.
{memory_section}
COGNITIVE GUIDELINES:
- Follow the reasoning plan above. It was generated by careful analysis of your task.
- Investigate the unknowns identified in the reasoning.
- Use web_search to find real information. Don't make things up.
- If your initial approach isn't working, ADAPT — try a different angle.
- You can dynamically **delegate sub-tasks** to specialized agents using the `delegate_task` tool. This spawns them in the background so you can keep working or spawn more!
- If you run into a blocker, broadcast a message to the "SwarmChannel" (using send_message) to ask if any other agent can help you (e.g. asking for a Python package or database built).
- Save important findings to files in your workspace using write_file.
- Be specific and concrete. Cite sources when possible.
- When done, provide: (1) key findings, (2) confidence level, (3) what remains unknown.
"""

    def _get_tool_handlers(self) -> Dict:
        if self.gateway:
            handlers = dict(self.gateway.make_tool_handlers(self.name))
        else:
            from .tools import TOOL_HANDLERS
            handlers = dict(TOOL_HANDLERS)

        async def handle_write_file(path: str, content: str) -> str:
            # Force strictly to workspace to prevent "gunk"
            safe_name = Path(path).name
            full_path = str(self.workspace / safe_name)
            if self.gateway:
                return await self.gateway.invoke_tool(self.name, "write_file", {"path": full_path, "content": content})
            from .tools import write_file
            return await write_file(full_path, content)
            
        handlers["write_file"] = handle_write_file

        async def handle_delegate_task(specialty: str, task: str) -> str:
            if self.depth >= 3:
                return "Error: Maximum delegation depth (3) reached. You must complete this task yourself without delegating further."
                
            from .agent import create_specialist_agent
            import uuid
            
            # Create a safe name for the sub-agent
            safe_domain = specialty.replace(' ', '_').replace('-', '_')[:20]
            name = f"Specialist_{safe_domain}_{uuid.uuid4().hex[:4]}"
            
            sub_agent = create_specialist_agent(
                name=name, specialty=specialty,
                hub=self.hub, workspace=self.workspace.parent / name.lower(),
                model=self.model, gateway=self.gateway, memory=self.memory,
                depth=self.depth + 1
            )
            
            if self.gateway:
                self.gateway.register_agent(name, sub_agent)
                
            task_id = f"del_{uuid.uuid4().hex[:6]}"
            from .state import Task
            t = Task(id=task_id, description=f"[Delegated from {self.name}] {task}. When complete, summarize and send_message back to {self.name}.")
            self.hub.add_task(t)
            
            self._log(f"Spawning background sub-agent '{name}' for task '{task_id}'...")
            
            # Non-blocking Swarm execution
            asyncio.create_task(sub_agent.execute(t))
            
            return f"Success. Sub-agent '{name}' spawned in the background for: {task}. They will send_message to '{self.name}' when complete. You may continue working or spawn additional parallel agents."

        handlers["delegate_task"] = handle_delegate_task
        return handlers

    def _is_simple_task(self, description: str) -> bool:
        """Detect if a task is simple enough to skip separate reasoning."""
        # Short tasks or straightforward instructions don't need a whole reasoning phase
        word_count = len(description.split())
        simple_signals = ['search for', 'find', 'look up', 'summarize', 'write a',
                          'list', 'compile', 'gather', 'check', 'verify']
        is_simple = word_count < 60 or any(s in description.lower() for s in simple_signals)
        return is_simple and self.depth >= 2  # Only skip reasoning for sub-agents

    def _build_history_context(self) -> str:
        """Build a compact summary of what this agent has done so far."""
        if not self._tasks_completed:
            return ""
        summary = "\n\nYOUR PRIOR WORK IN THIS SESSION:"
        for i, desc in enumerate(self._tasks_completed[-5:], 1):  # Last 5 tasks max
            summary += f"\n  {i}. {desc}"
        summary += "\n\nBuild on your prior work. Don't repeat what you've already done."
        return summary

    async def execute(self, task: Task) -> str:
        """Execute a task using the REASON -> ACT -> REFLECT loop.

        Features:
        - Conversation history persists across multiple task executions
        - Simple tasks skip the separate reasoning LLM call
        - Messages from other agents are injected as context
        - Results stored in memory for future reference
        """
        if self.gateway:
            self.gateway.register_task(task.id)

        self.hub.set_agent_status(self.name, "working", task.id,
                                   project_id=task.project_id, source_channel=task.source_channel)
        self.hub.update_task(task.id, status="in_progress", assigned_to=self.name)

        self._log(f"Starting task: {task.description[:80]}")

        # ── Phase 1: REASON (skip for simple sub-agent tasks) ─────
        is_simple = self._is_simple_task(task.description)

        if is_simple:
            reasoning_context = (
                "APPROACH: This is a focused task. Execute directly using your tools. "
                "Be thorough but efficient. Don't over-research — deliver concrete results."
            )
            self._log("Simple task — skipping separate reasoning call")
        else:
            reasoning_context = await self._reason_about_task(task.description)

        if self.gateway:
            self.gateway.log_trace(self.name, task.id, reasoning_context, "reasoning")

        # Check for messages from other agents
        messages_from_others = self.hub.get_messages(self.name)
        context_msgs = ""
        if messages_from_others:
            context_msgs = "\n\nMESSAGES FROM OTHER AGENTS:\n"
            for m in messages_from_others[-5:]:
                context_msgs += f"  From {m['sender']}: {m['content'][:300]}\n"

        # Build conversation history context
        history_context = self._build_history_context()

        # ── Phase 2: ACT ─────────────────────────────────────────
        system_prompt = self._system_prompt(task.description, reasoning_context)

        # If this agent has prior conversation history, include it for continuity
        if self._conversation_history:
            messages = [
                {"role": "system", "content": system_prompt},
                # Inject a summary of prior conversation as context
                *self._conversation_history[-10:],  # Last 10 messages max
                {"role": "user", "content": (
                    f"NEW TASK:\n\n{task.description}\n\n"
                    f"Build on your prior work above. Use your tools. Produce concrete results."
                    f"{context_msgs}{history_context}"
                )},
            ]
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    f"Execute this task now:\n\n{task.description}\n\n"
                    f"Follow your reasoning plan. Use your tools. Produce concrete results."
                    f"{context_msgs}{history_context}"
                )},
            ]

        tool_handlers = self._get_tool_handlers()

        async def on_tool_call(tool_name, args, result_preview):
            if self.gateway:
                await self.gateway.check_interrupt(task.id, self.name)
                self.gateway.log_trace(self.name, task.id, f"Calling tool: {tool_name}({str(args)[:50]}...)", "tool_call")
            self._log(f"  tool: {tool_name}({str(args)[:60]}...)")
            if self.progress_callback:
                try:
                    await self.progress_callback(_fmt_progress(self.name, tool_name, args), self.name)
                except Exception:
                    pass

        try:
            if self.gateway:
                await self.gateway.check_interrupt(task.id, self.name)

            result = await chat_with_tools(
                messages=messages,
                tool_defs=TOOL_DEFS,
                tool_handlers=tool_handlers,
                model=self.model,
                max_rounds=10,  # Reduced from 15 — prevents runaway tool loops
                on_tool_call=on_tool_call,
            )

            self.hub.update_task(task.id, status="done", result=result[:2000])
            self.hub.set_agent_status(self.name, "idle", project_id=task.project_id)
            self._log(f"Completed task: {task.description[:60]}...")

            # ── Persist conversation history ──────────────────────
            # Store a compact summary of this task + result for future context
            self._conversation_history.append(
                {"role": "assistant", "content": f"[Completed task: {task.description[:100]}]\n\nKey result:\n{result[:800]}"}
            )
            self._tasks_completed.append(f"{task.description[:80]} → {result[:60]}...")

            # Cap history to prevent unbounded growth
            if len(self._conversation_history) > 20:
                self._conversation_history = self._conversation_history[-15:]

            # Save result to workspace
            result_path = self.workspace / f"result_{task.id[:8]}.md"
            result_path.write_text(f"# Task: {task.description}\n\n## Result\n{result}")

            # ── Phase 3: REFLECT (store insights) ────────────────
            if self.memory and result and len(result) > 50:
                self.memory.store(
                    topic=task.description[:100],
                    content=result[:500],
                    category="research" if "Research" in self.name else "analysis",
                    source=self.name,
                    project=str(self.workspace.parent.parent.name),
                    confidence=0.6,
                )

            return result

        except asyncio.CancelledError:
            self.hub.update_task(task.id, status="killed", result="Terminated by Mission Control")
            self.hub.set_agent_status(self.name, "idle", project_id=task.project_id)
            self._log(f"Task {task.id} terminated by Mission Control")
            raise
        except Exception as e:
            error_msg = f"Failed: {e}"
            self.hub.update_task(task.id, status="failed", result=error_msg)
            self.hub.set_agent_status(self.name, "error", project_id=task.project_id)
            self._log(error_msg)

            # Record the failure in conversation history so the agent learns
            self._conversation_history.append(
                {"role": "assistant", "content": f"[FAILED task: {task.description[:80]}] Error: {str(e)[:200]}"}
            )

            if self.memory:
                self.memory.store_lesson(
                    what_happened=f"{self.name} failed on: {task.description[:100]}. Error: {str(e)[:200]}",
                    what_learned=f"Task type '{task.description[:50]}' may need different approach or model",
                    applies_to=task.description[:50],
                    project=str(self.workspace.parent.parent.name),
                )

            return error_msg

    def _log(self, message: str):
        line = f"[{self.name}] {message}"
        self._log_lines.append(line)
        print(line)


# ── Specialized Agent Factories ──────────────────────────────────────

def create_research_agent(hub: Hub, workspace: Path, model: str = "gpt-4.1-nano",
                          gateway: Any = None, memory: Optional[Memory] = None, depth: int = 0,
                          progress_callback: Optional[Callable] = None) -> Agent:
    return Agent(
        name="ResearchAgent",
        role=(
            "You are a research specialist. Your job is to search the web for high-quality, "
            "accurate information on the given topic. Find scientific papers, news articles, "
            "expert opinions, and data. Synthesize findings into clear, well-organized reports. "
            "Always cite your sources with URLs."
        ),
        hub=hub, workspace=workspace / "research", model=model,
        gateway=gateway, memory=memory, depth=depth, progress_callback=progress_callback,
    )


def create_analyst_agent(hub: Hub, workspace: Path, model: str = "gpt-4.1-nano",
                         gateway: Any = None, memory: Optional[Memory] = None, depth: int = 0,
                         progress_callback: Optional[Callable] = None) -> Agent:
    return Agent(
        name="AnalystAgent",
        role=(
            "You are a data analyst and critical thinker. Your job is to analyze information, "
            "identify patterns, evaluate evidence quality, find gaps in knowledge, and produce "
            "structured analyses. Use Python for calculations and data processing when needed. "
            "Be rigorous and evidence-based."
        ),
        hub=hub, workspace=workspace / "analysis", model=model,
        gateway=gateway, memory=memory, depth=depth, progress_callback=progress_callback,
    )


def create_writer_agent(hub: Hub, workspace: Path, model: str = "gpt-4.1-nano",
                        gateway: Any = None, memory: Optional[Memory] = None, depth: int = 0,
                        progress_callback: Optional[Callable] = None) -> Agent:
    return Agent(
        name="WriterAgent",
        role=(
            "You are a synthesis and writing specialist. Your job is to take research findings "
            "and analyses from other agents, and produce clear, comprehensive, well-structured "
            "reports. Focus on actionable insights and clear communication. Save final reports "
            "to your workspace."
        ),
        hub=hub, workspace=workspace / "reports", model=model,
        gateway=gateway, memory=memory, depth=depth, progress_callback=progress_callback,
    )


def create_specialist_agent(
    name: str, specialty: str, hub: Hub, workspace: Path,
    model: str = "gpt-4.1-nano", gateway: Any = None,
    memory: Optional[Memory] = None, depth: int = 0,
    progress_callback: Optional[Callable] = None,
) -> Agent:
    return Agent(
        name=name,
        role=f"You are a specialist in: {specialty}. Apply your expertise to the given task.",
        hub=hub, workspace=workspace / name.lower(), model=model,
        gateway=gateway, memory=memory, depth=depth, progress_callback=progress_callback,
    )
