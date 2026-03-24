"""Web channel — WebSocket handler for the built-in chat UI."""
from __future__ import annotations

import json
import asyncio
from uuid import uuid4
from typing import Dict

import aiohttp
from aiohttp import web


class WebChannel:
    """Handles WebSocket connections from the web chat UI."""

    def __init__(self, gateway):
        self.gateway = gateway
        self.connections: Dict[str, web.WebSocketResponse] = {}
        # Map session_id → project_id so we can scope pushes
        self._session_projects: Dict[str, str] = {}

        # Register telemetry broadcasts
        self.gateway.on_audit_event = self._broadcast_audit
        self.gateway.hub.on_status_change = self._broadcast_status
        self.gateway.hub.on_task_change = self._broadcast_task_change

    def _safe_push(self, coro):
        """Schedule a coroutine on the running event loop, safe from any calling context."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            pass

    def _broadcast_audit(self, entry):
        if isinstance(entry, dict):
            payload = dict(entry)
            if "type" not in payload:
                payload["type"] = "telemetry"
        else:
            payload = {
                "type": "telemetry",
                "agent": getattr(entry, "agent", "gateway"),
                "action": getattr(entry, "action", "audit"),
                "tool": getattr(entry, "tool", "internal"),
                "args": getattr(entry, "args_summary", ""),
                "allowed": getattr(entry, "allowed", True),
                "duration": getattr(entry, "duration_ms", 0.0),
                "task_id": getattr(entry, "task_id", ""),
            }

        # Attach project_id if missing — look it up via task_id or agent name
        if not payload.get("project_id"):
            try:
                task_id = payload.get("task_id", "")
                if task_id:
                    task = self.gateway.hub.get_task(task_id)
                    if task:
                        payload["project_id"] = task.project_id
                if not payload.get("project_id"):
                    agent_name = payload.get("agent", "")
                    statuses = self.gateway.hub.get_agent_statuses()
                    info = next((a for a in statuses if a["name"] == agent_name), {})
                    payload["project_id"] = info.get("project_id", "")
            except Exception:
                pass

        project_id = payload.get("project_id", "")
        self._safe_push(self._push_to_project(payload, project_id))

    def _broadcast_task_change(self, task_dict: dict):
        payload = {"type": "task_update", "task": task_dict}
        project_id = task_dict.get("project_id", "")
        self._safe_push(self._push_to_project(payload, project_id))

    def _broadcast_status(self, name: str, status: str, task: str):
        project_id = ""
        team_id = ""
        try:
            statuses = self.gateway.hub.get_agent_statuses()
            info = next((a for a in statuses if a["name"] == name), {})
            project_id = info.get("project_id", "")
            team_id = info.get("team_id", "")
        except Exception:
            pass
        payload = {
            "type": "agent_status",
            "agent": name,
            "status": status,
            "task": task,
            "project_id": project_id,
            "team_id": team_id,
        }
        self._safe_push(self._push_to_project(payload, project_id))
        
    def broadcast_team_event(self, event: dict):
        """Broadcast a team lifecycle event to all relevant sessions."""
        payload = {"type": "team_update", **event}
        project_id = event.get("project_id", "")
        self._safe_push(self._push_to_project(payload, project_id))

    async def push_to_all_json(self, payload: dict):
        for ws in list(self.connections.values()):
            if not ws.closed:
                try:
                    await ws.send_json(payload)
                except Exception:
                    pass

    async def _push_to_project(self, payload: dict, project_id: str):
        """Push to all sessions belonging to a specific project.
        If project_id is empty, broadcast to everyone (global events)."""
        if not project_id:
            await self.push_to_all_json(payload)
            return
        for sid, ws in list(self.connections.items()):
            if not ws.closed and self._session_projects.get(sid) == project_id:
                try:
                    await ws.send_json(payload)
                except Exception:
                    pass

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        session_id = request.query.get("session_id", "") or str(uuid4())
        user_id = request.query.get("user_id", "web_user")
        project_id = request.query.get("project_id", "")
        self.connections[session_id] = ws
        self._session_projects[session_id] = project_id

        # Send session ID back so client can persist it
        await ws.send_json({"type": "session", "session_id": session_id})

        # Send current roster on connect — filtered to this project only
        try:
            statuses = self.gateway.hub.get_agent_statuses()
            if project_id:
                statuses = [a for a in statuses if a.get("project_id") == project_id]
            await ws.send_json({"type": "roster_init", "agents": statuses})
        except Exception:
            pass

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        data = {"text": msg.data}

                    text = data.get("text", "").strip()
                    msg_type = data.get("type", "chat")
                    uid = data.get("user_id", user_id)

                    if msg_type == "get_teams":
                        try:
                            import json as _json
                            teams_raw = self.gateway.hub.recall("composer:org_design")
                            teams_data = _json.loads(teams_raw) if teams_raw else []
                            await ws.send_json({"type": "teams_init", "teams": teams_data})
                        except Exception:
                            await ws.send_json({"type": "teams_init", "teams": []})
                        continue

                    elif msg_type == "get_tasks":
                        try:
                            proj_filter = data.get("project_id", project_id)
                            all_tasks = self.gateway.hub.get_all_tasks()
                            if proj_filter:
                                all_tasks = [t for t in all_tasks if t.project_id == proj_filter]
                            await ws.send_json({
                                "type": "task_list",
                                "tasks": [t.to_dict() for t in all_tasks]
                            })
                        except Exception as e:
                            print(f"Error fetching tasks: {e}")
                        continue

                    elif msg_type == "get_sessions":
                        try:
                            # Fetch directly from backend DB bypassing LLM
                            sessions_db = self.gateway._chat_handler.sessions.list_sessions(user_id=uid, limit=30)
                            session_list = [{"id": s.session_id, "summary": s.context_summary or "New Session", "last_active": s.last_active} for s in sessions_db]
                            await ws.send_json({"type": "session_list", "sessions": session_list})
                        except Exception as e:
                            print(f"Error fetching sessions: {e}")
                        continue
                        
                    elif msg_type == "get_history":
                        try:
                            # Fetch chat history for this session to resume on refresh
                            history = self.gateway._chat_handler.sessions.get_context(session_id, limit=100)
                            await ws.send_json({"type": "history", "messages": history})
                        except Exception as e:
                            print(f"Error fetching history: {e}")
                        continue
                        
                    elif msg_type == "create_project":
                        name = data.get("name", "New Chat").strip() or "New Chat"
                        focus = data.get("focus", "")
                        try:
                            pid = self.gateway.hub.create_project(name, focus)
                            # Update session→project mapping so events route correctly
                            self._session_projects[session_id] = pid
                            project_id = pid
                            await ws.send_json({"type": "project_created", "id": pid, "name": name, "focus": focus})
                        except Exception as e:
                            await ws.send_json({"type": "error", "text": f"Failed to create project: {e}"})
                        continue

                    elif msg_type == "set_project":
                        project = data.get("project", "").strip()
                        if project:
                            # Inject this directly into long term memory
                            self.gateway._chat_handler.memory.store(
                                topic="Current User Project",
                                content=f"The user is currently focused exclusively on the project: {project}. Tailor responses to this.",
                                category="preference",
                                source="web_ui",
                                project="chat",
                                confidence=1.0
                            )
                            await ws.send_json({"type": "message", "text": f"*System: Project context switched to '{project}'.*"})
                        continue
                        
                    elif msg_type == "add_reminder":
                        desc = data.get("description", "")
                        when = data.get("when", "")
                        if desc and when:
                            try:
                                session_state = self.gateway._chat_handler.sessions.get_or_create(session_id, uid, "web")
                                handlers = self.gateway._chat_handler._build_tool_handlers(session_state)
                                res = await handlers["create_reminder"](description=desc, when=when)
                                await ws.send_json({"type": "message", "text": f"*System: {res}*"})
                            except Exception as e:
                                await ws.send_json({"type": "message", "text": f"*System: Failed to set reminder: {e}*"})
                        continue
                        
                    elif msg_type == "steer":
                        steer_text = data.get("text", "")
                        if steer_text:
                            # Trigger the Async LLM boundary interrupt
                            if hasattr(self.gateway._chat_handler, 'apply_steering'):
                                self.gateway._chat_handler.apply_steering(session_id, steer_text)
                                await ws.send_json({"type": "message", "text": f"*System: Steering command injected into active reasoning process.*"})
                        continue
                        
                    elif msg_type == "pause_task":
                        task_id = data.get("task_id")
                        if task_id:
                            self.gateway.pause_task(task_id)
                            await ws.send_json({"type": "message", "text": f"*System: Mission Control issued PAUSE for task {task_id}.*"})
                        continue
                        
                    elif msg_type == "resume_task":
                        task_id = data.get("task_id")
                        if task_id:
                            self.gateway.resume_task(task_id)
                            await ws.send_json({"type": "message", "text": f"*System: Mission Control issued RESUME for task {task_id}.*"})
                        continue
                        
                    elif msg_type == "stop_task":
                        task_id = data.get("task_id")
                        if task_id:
                            self.gateway.stop_task(task_id)
                            await ws.send_json({"type": "message", "text": f"*System: Mission Control issued TERMINATE for task {task_id}.*"})
                        continue

                    elif msg_type == "stop_project":
                        pid = data.get("project_id", project_id)
                        if pid:
                            try:
                                # Cancel the orchestrator asyncio task (real stop)
                                ch = getattr(self.gateway, '_chat_handler', None)
                                if ch:
                                    ch.cancel_project(pid)
                                # Mark all DB tasks killed and agents idle
                                self.gateway.hub.stop_project_tasks(pid)
                                await ws.send_json({"type": "project_stopped", "project_id": pid})
                            except Exception as e:
                                await ws.send_json({"type": "error", "text": f"Failed to stop project: {e}"})
                        continue

                    elif msg_type == "delete_project":
                        pid = data.get("project_id", project_id)
                        if pid:
                            try:
                                # Cancel the orchestrator asyncio task first
                                ch = getattr(self.gateway, '_chat_handler', None)
                                if ch:
                                    ch.cancel_project(pid)
                                self.gateway.hub.stop_project_tasks(pid)
                                self.gateway.hub.delete_project(pid)
                                await ws.send_json({"type": "project_deleted", "project_id": pid})
                            except Exception as e:
                                await ws.send_json({"type": "error", "text": f"Failed to delete project: {e}"})
                        continue

                    elif msg_type == "rename_project":
                        pid = data.get("project_id", project_id)
                        name = data.get("name", "").strip()
                        if pid and name:
                            try:
                                self.gateway.hub.rename_project(pid, name)
                                await ws.send_json({"type": "project_renamed", "project_id": pid, "name": name})
                            except Exception as e:
                                await ws.send_json({"type": "error", "text": f"Failed to rename project: {e}"})
                        continue

                    if not text:
                        continue

                    # Send typing indicator
                    await ws.send_json({"type": "typing", "status": True})

                    try:
                        response = await self.gateway.handle_user_message(
                            session_id=session_id,
                            user_id=uid,
                            channel="web",
                            text=text,
                            project_id=project_id,
                        )
                        await ws.send_json({"type": "message", "text": response})
                    except Exception as e:
                        await ws.send_json({
                            "type": "error",
                            "text": f"Error: {e}",
                        })
                    finally:
                        await ws.send_json({"type": "typing", "status": False})

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break
        finally:
            self.connections.pop(session_id, None)
            self._session_projects.pop(session_id, None)

        return ws

    async def C2_TERMINATE_ALL_CONNECTIONS(self):
        """Close all active WebSocket connections for a clean shutdown."""
        print(f"[C2 Hub Web] Definitive Shutdown Sequence Engaged in {__file__}")
        import aiohttp
        tasks = []
        for sid, ws in list(self.connections.items()):
            if not ws.closed:
                tasks.append(ws.close(code=aiohttp.WSCloseCode.GOING_AWAY, message='Server shutdown'))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.connections.clear()

    async def push_to_session(self, session_id: str, text: str):
        """Push a proactive message to a connected web session."""
        ws = self.connections.get(session_id)
        if ws and not ws.closed:
            try:
                await ws.send_json({"type": "proactive", "text": text})
            except Exception:
                pass

    async def push_to_all(self, text: str):
        """Push a message to all connected sessions."""
        for sid in list(self.connections):
            await self.push_to_session(sid, text)

    async def send_control_message(self, session_id: str, payload: dict):
        """Push a raw control JSON dict to a specific session."""
        ws = self.connections.get(session_id)
        if ws and not ws.closed:
            try:
                await ws.send_json(payload)
            except Exception:
                pass
        # Also update session→project if project_id is carried in payload
        if payload.get("project_id") and session_id:
            self._session_projects[session_id] = payload["project_id"]

    # ── Workspace C2 Endpoints ────────────────────────────────────

    async def handle_workspace_tree(self, request: web.Request) -> web.Response:
        """Returns the file tree of the workspace directory for the Web C2 Cockpit."""
        import os
        from pathlib import Path
        base_dir = getattr(self.gateway, 'project_dir', Path("."))

        def build_tree(dir_path):
            tree = []
            try:
                for entry in os.scandir(dir_path):
                    if entry.name.startswith(('__', '.')): continue
                    node = {"name": entry.name, "path": str(Path(entry.path).relative_to(base_dir))}
                    if entry.is_dir():
                        node["type"] = "directory"
                        node["children"] = build_tree(entry.path)
                    else:
                        node["type"] = "file"
                        node["size"] = entry.stat().st_size
                    tree.append(node)
                return sorted(tree, key=lambda x: (x["type"] != "directory", x["name"]))
            except Exception:
                return []
            
        try:
            return web.json_response(build_tree(base_dir))
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_workspace_file(self, request: web.Request) -> web.Response:
        """Returns raw file content for the Web C2 Cockpit file viewer."""
        path = request.query.get("path")
        if not path:
            return web.json_response({"error": "No path provided"}, status=400)
            
        try:
            from pathlib import Path
            base_dir = getattr(self.gateway, 'project_dir', Path(".")).resolve()
            full_path = (base_dir / path).resolve()
            
            # Prevent path traversal scaling
            if not str(full_path).startswith(str(base_dir)):
                return web.json_response({"error": "Path escaping detected. Permission denied."}, status=403)
                
            if not full_path.exists() or not full_path.is_file():
                return web.json_response({"error": "File not found"}, status=404)
                
            # If it's a binary file or unreadable, we just catch the decode error
            content = full_path.read_text(encoding="utf-8")
            return web.json_response({"content": content})
        except UnicodeDecodeError:
            return web.json_response({"error": "Binary file cannot be displayed."}, status=400)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
