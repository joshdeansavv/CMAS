"""Core chat handler — the brain of conversational mode."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Any, Callable

from .llm import chat_with_tools
from .tools import TOOL_DEFS, TOOL_HANDLERS
from .memory import Memory
from .reasoning import Reasoner
from .session import SessionManager, Session


# Extended tool definitions for chat mode
CHAT_EXTRA_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": (
                "Set a reminder for the user. Use this when the user asks to be reminded "
                "of something. Supports natural language time descriptions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What to remind the user about",
                    },
                    "when": {
                        "type": "string",
                        "description": (
                            "When to remind. ISO format (2025-03-20T14:00:00) or "
                            "relative like 'in 5 minutes', 'in 1 hour', 'tomorrow at 9am'"
                        ),
                    },
                },
                "required": ["description", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_scheduled_task",
            "description": "Create a recurring scheduled task (cron job). Runs automatically on schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What the task should do",
                    },
                    "cron": {
                        "type": "string",
                        "description": "Cron expression, e.g. '0 9 * * *' for daily at 9am, '*/30 * * * *' for every 30 min",
                    },
                },
                "required": ["description", "cron"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_scheduled_tasks",
            "description": "List all active reminders and scheduled tasks for this user.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_scheduled_task",
            "description": "Cancel a reminder or scheduled task by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "integer",
                        "description": "The ID of the job to cancel",
                    },
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deep_research",
            "description": (
                "Launch a thorough multi-agent research investigation on a topic. "
                "This runs in the background using multiple specialized agents "
                "(research, analysis, writing) and produces a comprehensive report. "
                "Use for complex questions that need deep investigation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "The research goal or question to investigate",
                    },
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": (
                "Save something to long-term memory. Use when the user asks you to "
                "remember something, or when you learn an important fact, preference, "
                "or insight worth retaining across conversations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Short topic label",
                    },
                    "content": {
                        "type": "string",
                        "description": "What to remember",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category: preference, fact, insight, task, or note",
                        "enum": ["preference", "fact", "insight", "task", "note"],
                    },
                },
                "required": ["topic", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Search long-term memory for information on a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for in memory",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command on the system. Use for system tasks, installing packages, managing files, starting servers, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30)",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_sessions",
            "description": "List the user's recent chat sessions with summaries.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_session",
            "description": "Switch the user's active UI to a different session ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "The exact session ID to switch to"}
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Pause your work and ask the user a direct question to get clarification or permission.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to ask"}
                },
                "required": ["question"],
            },
        },
    },
]


def _get_chat_tool_defs() -> list:
    """Full tool set for chat mode = base tools + chat extras."""
    return TOOL_DEFS + CHAT_EXTRA_TOOL_DEFS


def _parse_relative_time(when_str: str) -> float:
    """Parse relative time strings like 'in 5 minutes' to a unix timestamp."""
    import re
    now = time.time()
    when_lower = when_str.lower().strip()

    # Try ISO format first
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(when_str.strip(), fmt)
            return dt.timestamp()
        except ValueError:
            continue

    # Relative: "in X minutes/hours/days"
    m = re.search(r"in\s+(\d+)\s+(second|minute|hour|day|week)s?", when_lower)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        multipliers = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800}
        return now + amount * multipliers.get(unit, 60)

    # "tomorrow at Xam/pm"
    if "tomorrow" in when_lower:
        tomorrow = datetime.now().replace(hour=9, minute=0, second=0)
        from datetime import timedelta
        tomorrow += timedelta(days=1)
        m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", when_lower)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)
            ampm = m.group(3)
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            tomorrow = tomorrow.replace(hour=hour, minute=minute)
        return tomorrow.timestamp()

    # Default: 1 hour from now
    return now + 3600


class ChatHandler:
    """Handles conversational turns with tool use, memory, and context management."""

    def __init__(
        self,
        session_manager: SessionManager,
        memory: Memory,
        config: Any,
        scheduler_db_path: str = None,
    ):
        self.sessions = session_manager
        self.memory = memory
        self.config = config
        self.model = config.model
        self.reasoner = Reasoner(model=self.model)
        self._scheduler = None  # set by server after init
        self._push_callback: Optional[Callable] = None  # for pushing proactive messages
        self._control_callback: Optional[Callable] = None  # for pushing UI control commands
        self._db_path = scheduler_db_path or config.sqlite_path
        self._steering_queues: Dict[str, asyncio.Queue] = {}

    def apply_steering(self, session_id: str, text: str):
        if session_id not in self._steering_queues:
            self._steering_queues[session_id] = asyncio.Queue()
        self._steering_queues[session_id].put_nowait(text)

    def set_push_callback(self, cb: Callable):
        """Set callback for pushing messages to users: cb(session_id, channel, text)."""
        self._push_callback = cb

    def set_control_callback(self, cb: Callable):
        """Set callback for pushing UI system commands: cb(session_id, channel, payload_dict)."""
        self._control_callback = cb

    async def handle(self, session: Session, user_text: str) -> str:
        """Handle one user message and return a response."""
        
        self._steering_queues[session.session_id] = asyncio.Queue()
        def check_interrupt() -> Optional[str]:
            q = self._steering_queues.get(session.session_id)
            if q and not q.empty():
                return q.get_nowait()
            return None
            
        # Store user message
        self.sessions.add_message(
            session.session_id, session.user_id, "user",
            user_text, session.channel,
        )

        # Build context
        history = self.sessions.get_context(
            session.session_id, limit=self.config.max_context_messages,
        )

        # Search memory for relevant knowledge
        memory_context = ""
        try:
            entries = self.memory.search(user_text[:100], limit=5)
            if entries:
                memory_context = self.memory.format_for_context(entries, max_chars=1500)
        except Exception:
            pass

        # Build system prompt
        system_prompt = self._build_system_prompt(session, memory_context)

        # Build messages: system + context summary (if any) + recent history
        messages = [{"role": "system", "content": system_prompt}]
        if session.context_summary:
            messages.append({
                "role": "system",
                "content": f"Summary of earlier conversation:\n{session.context_summary}",
            })
        messages.extend(history)

        # Build tool handlers for this session
        tool_handlers = self._build_tool_handlers(session)

        # Call LLM with tools
        try:
            response = await chat_with_tools(
                messages=messages,
                tool_defs=_get_chat_tool_defs(),
                tool_handlers=tool_handlers,
                model=self.model,
                max_rounds=15,
                check_interrupt=check_interrupt,
            )
        except Exception as e:
            response = f"I encountered an error: {e}"

        # Store assistant response
        self.sessions.add_message(
            session.session_id, session.user_id, "assistant",
            response, session.channel,
        )

        # Store in vector memory if available
        try:
            if hasattr(self.memory, 'vector') and self.memory.vector:
                self.memory.vector.store_conversation(
                    doc_id=f"{session.session_id}_{time.time()}",
                    text=f"User: {user_text}\nAssistant: {response}",
                    metadata={
                        "session_id": session.session_id,
                        "user_id": session.user_id,
                        "timestamp": time.time(),
                    },
                )
        except Exception:
            pass

        return response

    def _build_system_prompt(self, session: Session, memory_context: str) -> str:
        now = datetime.now()
        try:
            if self.config.timezone:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(self.config.timezone)
                now = datetime.now(tz)
        except Exception:
            pass

        date_str = now.strftime("%A, %B %d, %Y at %I:%M %p")

        parts = [
            f"You are the central Routing Orchestrator for CMAS (Cognitive Multi-Agent System).",
            f"Current date/time: {date_str}",
            "",
            "CRITICAL INSTRUCTIONS:",
            "1. You are NOT a conversational chatbot. You are a high-level AGI task router.",
            "2. Whenever a user gives you a task, question, or goal that requires effort, DO NOT attempt to answer it directly using your own knowledge or simple web searches.",
            "3. You MUST physically spin up autonomous sub-agents using 'delegate_task' or launch the full cognitive Orchestrator using 'deep_research'.",
            "4. Only converse casually if the user is explicitly just saying 'hello'. Otherwise, deploy the swarm.",
            "5. If a user asks a complex scientific, medical, or engineering question, you MUST use 'deep_research'.",
            "6. A true AGI delegates. Use your tools immediately.",
            "",
            "CAPABILITIES:",
            "- Launch deep multi-agent research investigations (deep_research)",
            "- Dynamically delegate individual tasks to specialized sub-agents (delegate_task)",
            "- Set reminders and scheduled tasks (cron jobs)",
            "- Remember things across conversations using long-term memory",
        ]

        if memory_context:
            parts.append("")
            parts.append("RELEVANT MEMORIES:")
            parts.append(memory_context)

        # Load personality profile
        try:
            import yaml
            p_path = Path("personality.yaml")
            if p_path.exists():
                with open(p_path) as f:
                    p = yaml.safe_load(f)
                parts.append("")
                parts.append("PERSONALITY PROFILE:")
                if p.get("agent_name"): parts.append(f"Name: {p.get('agent_name')}")
                if p.get("focus"): parts.append(f"Focus: {p.get('focus')}")
                if p.get("tone"): parts.append(f"Tone: {p.get('tone')}")
                if p.get("directives"):
                    parts.append("Directives:")
                    for d in p.get("directives"):
                        parts.append(f" - {d}")
        except Exception:
            pass

        parts.append("")
        parts.append(f"Session: {session.session_id} | Channel: {session.channel}")

        return "\n".join(parts)

    def _build_tool_handlers(self, session: Session) -> Dict:
        """Build tool handlers with session context baked in."""
        from .tools import web_search, write_file, read_file, list_files, run_python, run_command

        handlers = {
            "web_search": web_search,
            "write_file": write_file,
            "read_file": read_file,
            "list_files": list_files,
            "run_python": run_python,
            "run_command": run_command,
        }

        # Session-aware handlers
        memory = self.memory

        async def handle_create_reminder(description: str, when: str, **kw) -> str:
            target_time = _parse_relative_time(when)
            return self._create_job(
                session, "reminder", description,
                schedule=when, next_run=target_time,
            )

        async def handle_create_scheduled_task(description: str, cron: str, **kw) -> str:
            try:
                from croniter import croniter
                next_run = croniter(cron, datetime.now()).get_next(float)
            except Exception:
                next_run = time.time() + 300
            return self._create_job(
                session, "cron", description,
                schedule=cron, next_run=next_run,
            )

        async def handle_list_scheduled_tasks(**kw) -> str:
            return self._list_jobs(session)

        async def handle_cancel_scheduled_task(job_id: int, **kw) -> str:
            return self._cancel_job(job_id, session)

        async def handle_deep_research(goal: str, **kw) -> str:
            asyncio.create_task(self._run_deep_research(goal, session))
            return f"Deep research started on: {goal}. I'll let you know when it's done."

        async def handle_remember(topic: str, content: str, category: str = "note", **kw) -> str:
            memory.store(
                topic=topic, content=content, category=category,
                source=f"user_{session.user_id}", project="chat",
                confidence=0.9,
            )
            return f"Saved to memory: [{category}] {topic}"

        async def handle_recall(query: str, **kw) -> str:
            entries = memory.search(query, limit=5)
            if not entries:
                return "No relevant memories found."
            return memory.format_for_context(entries, max_chars=2000)

        async def handle_send_message(recipient: str, content: str, **kw) -> str:
            return f"Message noted for {recipient}: {content}"

        async def handle_find_sessions(**kw) -> str:
            sessions = self.sessions.list_sessions(session.user_id, limit=10)
            if not sessions:
                return "No recent sessions found."
            lines = []
            for s in sessions:
                last_active = datetime.fromtimestamp(s.last_active).strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"Session: {s.session_id} | Last Active: {last_active} | Summary: {s.context_summary or 'No summary'}")
            return "Recent Sessions:\n" + "\n".join(lines)

        async def handle_switch_session(session_id: str, **kw) -> str:
            if hasattr(self, '_control_callback') and self._control_callback:
                await self._control_callback(session.session_id, session.channel, {"type": "session", "session_id": session_id})
                return f"Successfully commanded the user interface to switch to session '{session_id}'."
            return "Error: Control callback not configured. Cannot switch UI session natively."

        async def handle_ask_user(question: str, **kw) -> str:
            if self._push_callback:
                await self._push_callback(session.session_id, session.channel, f"❓ **Agent needs input**: {question}")
            
            q = self._steering_queues.setdefault(session.session_id, asyncio.Queue())
            answer = await q.get()
            return f"User replied: {answer}"

        async def handle_delegate_task(specialty: str, task: str, **kw) -> str:
            # Dynamically instantiate a specialist and map it to the Roster HUB natively!
            from .agent import create_specialist_agent
            from cmas.cli import get_project_dir
            proj_dir = get_project_dir(task[:20])
            agent = create_specialist_agent(
                f"Specialist_{specialty.replace(' ', '_')}", 
                specialty, 
                hub=self.gateway.hub if hasattr(self, 'gateway') else None,
                workspace=proj_dir, 
                model=self.model,
                gateway=self.gateway if hasattr(self, 'gateway') else None,
                memory=self.memory
            )
            
            # Spin up the agent in the background so it shows on the UI without blocking
            from .state import Task as AgentTask
            agt_task = AgentTask(id=f"delegated_{int(time.time())}", description=task)
            result = await agent.execute(agt_task)
            
            return f"Delegation to {specialty} completed. Findings:\n{result}"

        handlers["create_reminder"] = handle_create_reminder
        handlers["create_scheduled_task"] = handle_create_scheduled_task
        handlers["list_scheduled_tasks"] = handle_list_scheduled_tasks
        handlers["cancel_scheduled_task"] = handle_cancel_scheduled_task
        handlers["deep_research"] = handle_deep_research
        handlers["remember"] = handle_remember
        handlers["recall"] = handle_recall
        handlers["send_message"] = handle_send_message
        handlers["find_sessions"] = handle_find_sessions
        handlers["switch_session"] = handle_switch_session
        handlers["ask_user"] = handle_ask_user
        handlers["delegate_task"] = handle_delegate_task

        return handlers

    # ── Scheduler DB helpers ──────────────────────────────────────

    def _get_sched_conn(self):
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_job(self, session: Session, job_type: str, description: str,
                    schedule: str, next_run: float) -> str:
        conn = self._get_sched_conn()
        conn.execute(
            "INSERT INTO scheduled_jobs "
            "(job_type, description, schedule, action, session_id, user_id, channel, "
            "enabled, next_run, created_at) VALUES (?,?,?,?,?,?,?,1,?,?)",
            (job_type, description, schedule, json.dumps({"description": description}),
             session.session_id, session.user_id, session.channel,
             next_run, time.time()),
        )
        conn.commit()
        job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        when_str = datetime.fromtimestamp(next_run).strftime("%B %d at %I:%M %p")
        if job_type == "cron":
            return f"Scheduled task #{job_id} created: '{description}' (cron: {schedule})"
        return f"Reminder #{job_id} set: '{description}' — {when_str}"

    def _list_jobs(self, session: Session) -> str:
        conn = self._get_sched_conn()
        rows = conn.execute(
            "SELECT * FROM scheduled_jobs WHERE session_id = ? AND enabled = 1 "
            "ORDER BY next_run",
            (session.session_id,),
        ).fetchall()
        conn.close()

        if not rows:
            return "No active reminders or scheduled tasks."

        lines = []
        for r in rows:
            next_str = datetime.fromtimestamp(r["next_run"]).strftime("%b %d %I:%M %p") if r["next_run"] else "?"
            lines.append(f"  #{r['id']} [{r['job_type']}] {r['description']} — next: {next_str}")
        return "Active tasks:\n" + "\n".join(lines)

    def _cancel_job(self, job_id: int, session: Session) -> str:
        conn = self._get_sched_conn()
        conn.execute(
            "UPDATE scheduled_jobs SET enabled = 0 WHERE id = ? AND session_id = ?",
            (job_id, session.session_id),
        )
        conn.commit()
        conn.close()
        return f"Task #{job_id} cancelled."

    # ── Deep Research ─────────────────────────────────────────────

    async def _run_deep_research(self, goal: str, session: Session):
        """Run the full orchestrator in the background and push result when done."""
        try:
            from .orchestrator import Orchestrator
            from cmas.cli import get_project_dir

            project_dir = get_project_dir(goal)
            orchestrator = Orchestrator(
                project_dir=project_dir,
                model=self.config.research_model,
                agent_model=self.config.model,
                max_iterations=3,
                local_timezone=self.config.timezone,
            )
            result = await orchestrator.run(goal)

            summary = result[:500] if isinstance(result, str) else str(result)[:500]
            report_path = project_dir / "final_report.md"
            msg = f"Deep research complete: {goal}\n\nSummary: {summary}"
            if report_path.exists():
                msg += f"\n\nFull report saved to: {report_path}"

            if self._push_callback:
                await self._push_callback(session.session_id, session.channel, msg)
        except Exception as e:
            if self._push_callback:
                await self._push_callback(
                    session.session_id, session.channel,
                    f"Deep research failed: {e}",
                )
