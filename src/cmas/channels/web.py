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

        # Register telemetry broadcasts
        if hasattr(self.gateway, 'on_audit_event'):
            self.gateway.on_audit_event = self._broadcast_audit

        if hasattr(self.gateway.hub, 'on_status_change'):
            self.gateway.hub.on_status_change = self._broadcast_status

    def _broadcast_audit(self, entry):
        if isinstance(entry, dict):
            payload = entry
            if "type" not in payload: payload["type"] = "telemetry"
        else:
            payload = {
                "type": "telemetry",
                "agent": getattr(entry, "agent", "gateway"),
                "action": getattr(entry, "action", "audit"),
                "tool": getattr(entry, "tool", "internal"),
                "args": getattr(entry, "args_summary", ""),
                "allowed": getattr(entry, "allowed", True),
                "duration": getattr(entry, "duration_ms", 0.0)
            }
        asyncio.create_task(self.push_to_all_json(payload))
        
    def _broadcast_status(self, name: str, status: str, task: str):
        payload = {
            "type": "agent_status",
            "agent": name,
            "status": status,
            "task": task
        }
        asyncio.create_task(self.push_to_all_json(payload))
        
    async def push_to_all_json(self, payload: dict):
        for ws in list(self.connections.values()):
            if not ws.closed:
                try:
                    await ws.send_json(payload)
                except Exception:
                    pass

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        session_id = request.query.get("session_id", str(uuid4()))
        user_id = request.query.get("user_id", "web_user")
        self.connections[session_id] = ws

        # Send session ID back so client can persist it
        await ws.send_json({"type": "session", "session_id": session_id})

        # Send current roster on connect
        try:
            statuses = self.gateway.hub.get_agent_statuses()
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

                    if msg_type == "get_sessions":
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
        """Push a raw control JSON dict to a session (e.g., to force UI changes)."""
        ws = self.connections.get(session_id)
        if ws and not ws.closed:
            try:
                await ws.send_json(payload)
            except Exception:
                pass

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
