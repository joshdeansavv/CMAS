"""Gateway — central routing, access control, rate limiting, and audit layer.

Sits between agents and all external resources (tools, APIs, other agents).
The orchestrator manages *strategy*; the gateway manages *operations*.
"""
from __future__ import annotations

import asyncio
import json
import time
import subprocess
import importlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from .state import Hub


# ── Access Control ───────────────────────────────────────────────────

# Default permissions: which agent types can use which tools
DEFAULT_PERMISSIONS = {
    "ResearchAgent": {"web_search", "write_file", "read_file", "list_files", "run_python", "send_message"},
    "AnalystAgent":  {"web_search", "write_file", "read_file", "list_files", "run_python", "send_message"},
    "WriterAgent":   {"write_file", "read_file", "list_files", "run_python", "send_message"},
    # Specialists get everything by default
    "_default":      {"web_search", "write_file", "read_file", "list_files", "run_python", "send_message"},
}


@dataclass
class RateLimitState:
    """Track rate limiting per agent per tool."""
    calls: List[float] = field(default_factory=list)

    def check(self, max_calls: int, window_secs: float) -> bool:
        """Return True if the call is allowed."""
        now = time.time()
        # Prune old entries
        self.calls = [t for t in self.calls if now - t < window_secs]
        if len(self.calls) >= max_calls:
            return False
        self.calls.append(now)
        return True


@dataclass
class AuditEntry:
    timestamp: float
    agent: str
    action: str
    tool: str
    args_summary: str
    result_summary: str
    allowed: bool
    task_id: str = ""
    reasoning: str = ""
    duration_ms: float = 0.0


class Gateway:
    """Central operations hub for the multi-agent system.

    Responsibilities:
    - Route all tool calls through access control + rate limiting
    - Route inter-agent messages
    - Audit log every action
    - Detect and prevent infinite loops / runaway agents
    - Manage package installation on demand
    - Provide wrapped tool handlers that agents use transparently
    """

    def __init__(
        self,
        hub: Hub,
        project_dir: Path,
        permissions: Optional[Dict[str, set]] = None,
        rate_limit_calls: int = 30,
        rate_limit_window: float = 60.0,
        max_recursion_depth: int = 5,
    ):
        self.hub = hub
        self.project_dir = project_dir
        self.permissions = permissions or DEFAULT_PERMISSIONS
        self.rate_limit_calls = rate_limit_calls
        self.rate_limit_window = rate_limit_window
        self.max_recursion_depth = max_recursion_depth

        # State tracking
        self._rate_limits: Dict[str, Dict[str, RateLimitState]] = defaultdict(lambda: defaultdict(RateLimitState))
        self._audit_log: List[AuditEntry] = []
        self._agent_call_depth: Dict[str, int] = defaultdict(int)
        self._registered_agents: Dict[str, Any] = {}
        self._installed_packages: set = set()
        self.on_audit_event = None
        self._lock = asyncio.Lock()
        
        # Mission Control C2 Hooks
        self._task_pause_events: Dict[str, asyncio.Event] = {}
        self._task_stop_events: Dict[str, asyncio.Event] = {}
        self._agent_traces: Dict[str, List[Dict]] = defaultdict(list)
        self.hub.on_message = self._on_hub_message

        self._print("Gateway Mission Control active")

    def _on_hub_message(self, sender, recipient, content):
        """Broadcast inter-agent communication for visualization."""
        self.broadcast_telemetry({
            "type": "comm",
            "ts": time.strftime("%H:%M:%S"),
            "from": sender,
            "to": recipient,
            "text": content[:200]
        })

    def broadcast_telemetry(self, payload: dict):
        """Broadcast a real-time event to the C2 Cockpit."""
        if self.on_audit_event:
            self.on_audit_event(payload)

    def _print(self, msg: str):
        print(f"[Gateway] {msg}")

    # ── Agent Registration ───────────────────────────────────────

    def register_agent(self, name: str, agent: Any):
        """Register an agent with the gateway."""
        self._registered_agents[name] = agent
        self._print(f"Registered agent: {name}")

    def get_registered_agents(self) -> List[str]:
        return list(self._registered_agents.keys())

    # ── Access Control ───────────────────────────────────────────

    def _check_permission(self, agent_name: str, tool_name: str) -> bool:
        """Check if an agent has permission to use a tool."""
        allowed_tools = self.permissions.get(agent_name, self.permissions.get("_default", set()))
        return tool_name in allowed_tools

    def grant_permission(self, agent_name: str, tool_name: str):
        """Dynamically grant a permission to an agent."""
        if agent_name not in self.permissions:
            self.permissions[agent_name] = set(self.permissions.get("_default", set()))
        self.permissions[agent_name].add(tool_name)
        self._print(f"Granted {agent_name} access to {tool_name}")

    def revoke_permission(self, agent_name: str, tool_name: str):
        """Revoke a permission from an agent."""
        if agent_name in self.permissions:
            self.permissions[agent_name].discard(tool_name)
            self._print(f"Revoked {agent_name} access to {tool_name}")

    # ── Rate Limiting ────────────────────────────────────────────

    def _check_rate_limit(self, agent_name: str, tool_name: str) -> bool:
        """Check if an agent is within rate limits for a tool."""
        state = self._rate_limits[agent_name][tool_name]
        return state.check(self.rate_limit_calls, self.rate_limit_window)

    # ── Task Interruption & Mission Control ──────────────────────

    def register_task(self, task_id: str):
        """Register a task to be externally controllable via C2."""
        self._task_pause_events[task_id] = asyncio.Event()
        self._task_pause_events[task_id].set()  # Default: Not Paused
        self._task_stop_events[task_id] = asyncio.Event()

    def pause_task(self, task_id: str):
        if task_id in self._task_pause_events:
            self._task_pause_events[task_id].clear()
            self._audit("Gateway_C2", "intervene", "pause_task", f"target={task_id}", "", True)
            self._print(f"Task {task_id} PAUSED by Mission Control.")

    def resume_task(self, task_id: str):
        if task_id in self._task_pause_events:
            self._task_pause_events[task_id].set()
            self._audit("Gateway_C2", "intervene", "resume_task", f"target={task_id}", "", True)
            self._print(f"Task {task_id} RESUMED by Mission Control.")

    def stop_task(self, task_id: str):
        if task_id in self._task_stop_events:
            self._task_stop_events[task_id].set()
            if task_id in self._task_pause_events:
                self._task_pause_events[task_id].set()  # Unblock if asleep to allow death
            self._audit("Gateway_C2", "intervene", "terminate_task", f"target={task_id}", "", True)
            self._print(f"Task {task_id} TERMINATED by Mission Control.")

    async def check_interrupt(self, task_id: str, agent_name: str = "Unknown"):
        """Hardware-level interception. Halts the script if paused."""
        if task_id in self._task_stop_events and self._task_stop_events[task_id].is_set():
            raise asyncio.CancelledError(f"Task {task_id} was externally TERMiNATED by Mission Control.")
        
        if task_id in self._task_pause_events and not self._task_pause_events[task_id].is_set():
            self._print(f"[{agent_name}] INTERCEPTED: Agent sleeping due to Mission Control Pause...")
            task = self.hub.get_task(task_id)
            pid = task.project_id if task else ""
            self.hub.set_agent_status(agent_name, "paused", task_id, project_id=pid)
            await self._task_pause_events[task_id].wait()
            self._print(f"[{agent_name}] AWOKEN: Agent resuming operations...")
            self.hub.set_agent_status(agent_name, "working", task_id, project_id=pid)

    # ── Loop / Recursion Detection ───────────────────────────────

    def enter_call(self, agent_name: str) -> bool:
        """Track call depth. Returns False if max recursion exceeded."""
        self._agent_call_depth[agent_name] += 1
        if self._agent_call_depth[agent_name] > self.max_recursion_depth:
            self._print(f"CIRCUIT BREAKER: {agent_name} exceeded max recursion depth ({self.max_recursion_depth})")
            return False
        return True

    def exit_call(self, agent_name: str):
        """Decrement call depth."""
        self._agent_call_depth[agent_name] = max(0, self._agent_call_depth[agent_name] - 1)

    # ── Audit Log ────────────────────────────────────────────────

    def _audit(self, agent: str, action: str, tool: str, args_summary: str,
               result_summary: str, allowed: bool, duration_ms: float = 0.0,
               task_id: str = "", reasoning: str = ""):
        entry = AuditEntry(
            timestamp=time.time(),
            agent=agent,
            action=action,
            tool=tool,
            args_summary=args_summary[:200],
            result_summary=result_summary[:200],
            allowed=allowed,
            duration_ms=duration_ms,
            task_id=task_id,
            reasoning=reasoning
        )
        self._audit_log.append(entry)

        if self.on_audit_event:
            try:
                payload = {
                    "type": "telemetry",
                    "ts": time.strftime("%H:%M:%S"),
                    "agent": getattr(entry, "agent", "gateway"),
                    "action": getattr(entry, "action", "audit"),
                    "tool": getattr(entry, "tool", "internal"),
                    "args": getattr(entry, "args_summary", ""),
                    "result": getattr(entry, "result_summary", ""),
                    "allowed": getattr(entry, "allowed", True),
                    "task_id": getattr(entry, "task_id", ""),
                    "reasoning": getattr(entry, "reasoning", "")
                }
                self.on_audit_event(payload)
            except Exception:
                pass

        # Also persist to hub
        self.hub.send_message(
            sender="gateway",
            recipient="AuditLog",
            content=f"[{entry.agent}] {entry.tool}({entry.args_summary}) -> {entry.result_summary}"
        )

    def log_trace(self, agent_name: str, task_id: str, content: str, step_type: str = "reasoning"):
        """Log a specific decision trace for the C2 Cockpit HUD."""
        entry = {
            "ts": time.time(),
            "type": step_type,
            "content": content
        }
        self._agent_traces[agent_name].append(entry)
        
        if self.on_audit_event:
            self.on_audit_event({
                "type": "trace",
                "agent": agent_name,
                "task_id": task_id,
                "step_type": step_type,
                "content": content,
                "ts": time.strftime("%H:%M:%S")
            })

    def get_audit_log(self, agent: Optional[str] = None, limit: int = 50) -> List[AuditEntry]:
        """Get recent audit entries, optionally filtered by agent."""
        entries = self._audit_log
        if agent:
            entries = [e for e in entries if e.agent == agent]
        return entries[-limit:]

    def get_audit_summary(self) -> str:
        """Human-readable audit summary."""
        if not self._audit_log:
            return "No activity logged."

        lines = ["=== Gateway Audit Summary ==="]
        by_agent = defaultdict(lambda: {"total": 0, "denied": 0, "tools": defaultdict(int)})
        for e in self._audit_log:
            s = by_agent[e.agent]
            s["total"] += 1
            if not e.allowed:
                s["denied"] += 1
            s["tools"][e.tool] += 1

        for agent_name, stats in by_agent.items():
            lines.append(f"\n  {agent_name}: {stats['total']} calls ({stats['denied']} denied)")
            for tool, count in stats["tools"].items():
                lines.append(f"    {tool}: {count}")

        return "\n".join(lines)

    # ── Message Routing ──────────────────────────────────────────

    async def route_message(self, sender: str, recipient: str, content: str) -> str:
        """Route a message between agents through the gateway."""
        self._audit(sender, "message", "send_message",
                    f"to={recipient}", content[:100], True)
        self.hub.send_message(sender, recipient, content)
        self._print(f"Message: {sender} -> {recipient} ({len(content)} chars)")
        return f"Message delivered to {recipient}"

    async def get_messages_for(self, agent_name: str, since: float = 0) -> List[Dict]:
        """Get pending messages for an agent."""
        return self.hub.get_messages(agent_name, since=since)

    # ── Package Installation ─────────────────────────────────────

    async def install_package(self, package_name: str, requested_by: str = "system") -> str:
        """Install a Python package on demand."""
        if package_name in self._installed_packages:
            return f"Already installed: {package_name}"

        self._audit(requested_by, "install", "pip", package_name, "", True)

        try:
            importlib.import_module(package_name.split("[")[0].replace("-", "_"))
            self._installed_packages.add(package_name)
            return f"Already available: {package_name}"
        except ImportError:
            pass

        self._print(f"Installing package: {package_name} (requested by {requested_by})")
        try:
            result = subprocess.run(
                ["python3", "-m", "pip", "install", "-q", package_name],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                self._installed_packages.add(package_name)
                self._print(f"Installed: {package_name}")
                return f"Installed: {package_name}"
            else:
                error = result.stderr[:500]
                self._print(f"Failed to install {package_name}: {error}")
                return f"Failed: {error}"
        except Exception as e:
            return f"Install error: {e}"

    # ── Tool Call Routing (the core gateway function) ─────────────

    async def invoke_tool(self, agent_name: str, tool_name: str, args: Dict) -> str:
        """Route a tool call through access control, rate limiting, and auditing.

        This is the single entry point for all agent tool usage.
        """
        args_summary = json.dumps(args)[:200]

        # 1. Access control
        if not self._check_permission(agent_name, tool_name):
            self._audit(agent_name, "denied", tool_name, args_summary, "permission denied", False)
            self._print(f"DENIED: {agent_name} tried to use {tool_name} (no permission)")
            return f"Error: {agent_name} does not have permission to use {tool_name}"

        # 2. Rate limiting
        if not self._check_rate_limit(agent_name, tool_name):
            self._audit(agent_name, "rate_limited", tool_name, args_summary, "rate limited", False)
            self._print(f"RATE LIMITED: {agent_name} on {tool_name}")
            return f"Error: rate limit exceeded for {tool_name}. Wait before retrying."

        # 3. Recursion check
        if not self.enter_call(agent_name):
            self._audit(agent_name, "circuit_break", tool_name, args_summary, "max recursion", False)
            return f"Error: {agent_name} exceeded maximum call depth. Stopping to prevent infinite loop."

        # 4. Execute the tool
        start = time.time()
        try:
            # Import the actual tool handlers
            from .tools import TOOL_HANDLERS
            handler = TOOL_HANDLERS.get(tool_name)
            if not handler:
                result = f"Error: unknown tool '{tool_name}'"
                self._audit(agent_name, "error", tool_name, args_summary, result, True)
                return result

            result = await handler(**args)
            if not isinstance(result, str):
                result = json.dumps(result)

            duration = (time.time() - start) * 1000
            self._audit(agent_name, "success", tool_name, args_summary, result[:200], True, duration)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            error = f"Error: {e}"
            self._audit(agent_name, "error", tool_name, args_summary, error, True, duration)
            return error

        finally:
            self.exit_call(agent_name)

    # ── Gateway-Wrapped Tool Handlers ────────────────────────────

    def make_tool_handlers(self, agent_name: str) -> Dict[str, Callable]:
        """Create a set of tool handlers for a specific agent, routed through the gateway.

        These handlers have the same signatures as the raw tools,
        but go through access control, rate limiting, and auditing.
        """
        gateway = self

        async def web_search(query: str, max_results: int = 5) -> str:
            return await gateway.invoke_tool(agent_name, "web_search", {"query": query, "max_results": max_results})

        async def write_file(path: str, content: str) -> str:
            return await gateway.invoke_tool(agent_name, "write_file", {"path": path, "content": content})

        async def read_file(path: str) -> str:
            return await gateway.invoke_tool(agent_name, "read_file", {"path": path})

        async def list_files(directory: str) -> str:
            return await gateway.invoke_tool(agent_name, "list_files", {"directory": directory})

        async def run_python(code: str) -> str:
            return await gateway.invoke_tool(agent_name, "run_python", {"code": code})

        async def send_message(recipient: str, content: str) -> str:
            return await gateway.route_message(agent_name, recipient, content)

        return {
            "web_search": web_search,
            "write_file": write_file,
            "read_file": read_file,
            "list_files": list_files,
            "run_python": run_python,
            "send_message": send_message,
        }

    # ── Chat Message Routing (session-aware) ────────────────────

    async def handle_user_message(
        self, session_id: str, user_id: str, channel: str, text: str,
        project_id: str = "",
    ) -> str:
        """Entry point for all user messages from any channel.

        Routes through the chat handler and audits the interaction.
        """
        self._audit(user_id, "user_message", channel, text[:200], "", True)

        if not hasattr(self, '_chat_handler') or self._chat_handler is None:
            return "System not ready — chat handler not initialized."

        session = self._chat_handler.sessions.get_or_create(
            session_id, user_id, channel, project_id
        )

        response = await self._chat_handler.handle(session, text)

        self._audit("cmas", "response", channel, response[:200], "", True)
        return response

    def set_chat_handler(self, handler):
        """Set the chat handler for user message routing."""
        self._chat_handler = handler

    # ── Health Check ─────────────────────────────────────────────

    def health_check(self) -> Dict:
        """Get system health: agent statuses, stuck agents, rate limit state."""
        agents = self.hub.get_agent_statuses()
        stuck = []
        for a in agents:
            if a["status"] == "working" and (time.time() - a["updated_at"]) > 300:
                stuck.append(a["name"])

        return {
            "registered_agents": len(self._registered_agents),
            "active_agents": sum(1 for a in agents if a["status"] == "working"),
            "stuck_agents": stuck,
            "total_tool_calls": len(self._audit_log),
            "denied_calls": sum(1 for e in self._audit_log if not e.allowed),
            "installed_packages": list(self._installed_packages),
        }

    def get_status(self) -> str:
        """Human-readable gateway status."""
        h = self.health_check()
        lines = [
            "=== Gateway Status ===",
            f"  Agents registered: {h['registered_agents']}",
            f"  Active agents: {h['active_agents']}",
            f"  Stuck agents: {h['stuck_agents'] or 'none'}",
            f"  Total tool calls: {h['total_tool_calls']}",
            f"  Denied calls: {h['denied_calls']}",
            f"  Installed packages: {len(h['installed_packages'])}",
        ]
        return "\n".join(lines)
