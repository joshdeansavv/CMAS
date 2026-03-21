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

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        session_id = request.query.get("session_id", str(uuid4()))
        user_id = request.query.get("user_id", "web_user")
        self.connections[session_id] = ws

        # Send session ID back so client can persist it
        await ws.send_json({"type": "session", "session_id": session_id})

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        data = {"text": msg.data}

                    text = data.get("text", "").strip()
                    if not text:
                        continue

                    uid = data.get("user_id", user_id)

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
