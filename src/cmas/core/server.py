"""aiohttp server — serves web UI, WebSocket, and webhook routes."""
from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import web

from .config import Config
from .state import Hub
from .gateway import Gateway
from .memory import Memory
from .session import SessionManager
from .chat import ChatHandler
from ..channels.web import WebChannel

WEB_DIR = Path(__file__).resolve().parent.parent / "web-app" / "dist"


class CMASServer:
    """Single-process server running everything in one event loop."""

    def __init__(self, config: Config):
        self.config = config

        # Core modules
        self.memory = Memory()
        self.hub = Hub(config.workspace_dir)
        self.gateway = Gateway(
            hub=self.hub,
            project_dir=config.workspace_dir,
            rate_limit_calls=30,
            rate_limit_window=60.0,
        )
        self.session_manager = SessionManager(config.sqlite_path)
        self.chat_handler = ChatHandler(
            session_manager=self.session_manager,
            memory=self.memory,
            config=config,
            scheduler_db_path=config.sqlite_path,
        )
        self.chat_handler.gateway = self.gateway
        self.gateway.set_chat_handler(self.chat_handler)

        # Channels (Strictly localhost web interface for now)
        self.web_channel = WebChannel(self.gateway)
        print(f"[C2 Hub Debug] WebChannel instance type: {type(self.web_channel)}")
        import inspect
        print(f"[C2 Hub Debug] Source file for WebChannel: {inspect.getfile(WebChannel)}")
        self.channels = {"web": self.web_channel}

        # Set up push callback for proactive messages
        self.chat_handler.set_push_callback(self._push_to_session)
        self.chat_handler.set_control_callback(self._push_control_to_session)

        # Background tasks
        self._background_tasks = []

    async def _push_to_session(self, session_id: str, channel: str, text: str):
        """Push a message to a user session on the right channel."""
        adapter = self.channels.get(channel)
        if adapter:
            await adapter.push_to_session(session_id, text)

    async def _push_control_to_session(self, session_id: str, channel: str, payload: dict):
        """Push a raw control dictionary to the web channel UI."""
        adapter = self.channels.get(channel)
        if adapter and hasattr(adapter, 'send_control_message'):
            await adapter.send_control_message(session_id, payload)

    def _build_app(self) -> web.Application:
        app = web.Application()

        # WebSocket endpoint
        app.router.add_get("/ws", self.web_channel.websocket_handler)

        # API Endpoints
        app.router.add_get("/api/workspace", self.web_channel.handle_workspace_tree)
        app.router.add_get("/api/workspace/file", self.web_channel.handle_workspace_file)

        # Static web UI
        if WEB_DIR.exists():
            app.router.add_get("/", self._serve_index)
            # Vite bundles its static files in /assets
            app.router.add_static("/assets", str(WEB_DIR / "assets"), name="assets")
            # Also serve root static files if any (like favicon)
            app.router.add_static("/", str(WEB_DIR), name="static", show_index=False)

        # APIs
        app.router.add_get("/health", self._health_handler)
        app.router.add_get("/api/workspace", self._workspace_handler)
        app.router.add_get("/api/workspace/file", self._file_handler)
        app.router.add_get("/api/projects", self._projects_handler)

        # External channels explicitly disabled to isolate localhost gateway
        return app

    async def _serve_index(self, request: web.Request) -> web.Response:
        index = WEB_DIR / "index.html"
        if index.exists():
            return web.FileResponse(index)
        return web.Response(text="CMAS is running. Web UI not found.", status=200)

    async def _health_handler(self, request: web.Request) -> web.Response:
        import json
        health = self.gateway.health_check()
        health["sessions"] = len(self.web_channel.connections)
        return web.json_response(health)

    async def _workspace_handler(self, request: web.Request) -> web.Response:
        """Browse the current mission workspace."""
        path = self.config.workspace_path
        def _get_tree(p):
            res = []
            if not p.exists(): return res
            for child in p.iterdir():
                if child.name.startswith("."): continue
                node = {"name": child.name, "path": str(child), "type": "directory" if child.is_dir() else "file"}
                if child.is_dir():
                    node["children"] = _get_tree(child)
                res.append(node)
            return sorted(res, key=lambda x: (x["type"] == "file", x["name"]))
        tree = _get_tree(path)
        return web.json_response(tree)

    async def _file_handler(self, request: web.Request) -> web.Response:
        """Read a file from the workspace."""
        file_path = request.query.get("path")
        if not file_path: return web.Response(status=400)
        p = Path(file_path)
        if not p.exists() or p.is_dir(): return web.Response(status=404)
        try:
            return web.json_response({"content": p.read_text()})
        except Exception:
            return web.Response(status=500, text="Unable to read file")

    async def _projects_handler(self, request: web.Request) -> web.Response:
        """List active C2 mission projects."""
        projects = self.hub.get_projects()
        return web.json_response(projects)

    # External platforms like Discord disconnected by C2 architectural mandate

    async def _start_scheduler(self):
        """Start background scheduler if enabled."""
        if not self.config.scheduler_enabled:
            return
        try:
            from .scheduler import Scheduler
            scheduler = Scheduler(
                db_path=self.config.sqlite_path,
                chat_handler=self.chat_handler,
                memory=self.memory,
                config=self.config,
                push_callback=self._push_to_session,
            )
            self.chat_handler._scheduler = scheduler
            task = asyncio.create_task(scheduler.run_forever())
            self._background_tasks.append(task)
            print("[Server] Background scheduler started")
        except Exception as e:
            print(f"[Server] Scheduler setup failed: {e}")

    async def _start_vector_memory(self):
        """Initialize ChromaDB vector memory if available."""
        try:
            from .vector import VectorMemory
            vector = VectorMemory(persist_dir=self.config.vector_db_path)
            self.memory.vector = vector
            print("[Server] Vector memory (ChromaDB) initialized")
        except ImportError:
            print("[Server] ChromaDB not installed — using text search only (pip install chromadb to enable)")
        except Exception as e:
            print(f"[Server] Vector memory setup failed: {e}")

    async def start(self):
        """Start the full CMAS server."""
        print(f"\n  >>> C2 MISSION CONTROL VERIFIED BOOT [Revision 42] <<<")
        print(f"  CMAS — Always-On Agent")
        print(f"  {'─'*40}")
        print(f"  Model: {self.config.model}")
        if self.config.timezone:
            print(f"  Timezone: {self.config.timezone}")
        print(f"  Workspace: {self.config.workspace_dir}")
        print()

        # Initialize optional components
        await self._start_vector_memory()
        await self._start_scheduler()

        # Build and start HTTP server
        app = self._build_app()
        runner = web.AppRunner(app)
        await runner.setup()
        
        # When host is "0.0.0.0", bind to all interfaces (IPv4 and IPv6) to allow localhost to work
        bind_host = None if self.config.host == "0.0.0.0" else self.config.host
        site = web.TCPSite(runner, bind_host, self.config.port)
        await site.start()

        url = f"http://localhost:{self.config.port}"
        print(f"  {'─'*40}")
        print(f"  Web UI:  {url}")
        print(f"  WS:      ws://localhost:{self.config.port}/ws")
        print(f"  Health:  {url}/health")
        print(f"  {'─'*40}")
        print(f"  Ready. Open {url} to command the Swarm natively.\n")

        # Keep running forever
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[Mission Control] Safety Shutdown engaged... cleaning up Gateway C2 loops.")
            for task in self._background_tasks:
                task.cancel()
            if hasattr(self, 'web_channel') and hasattr(self.web_channel, 'C2_TERMINATE_ALL_CONNECTIONS'):
                print("[C2 Server Hub] Calling C2_TERMINATE_ALL_CONNECTIONS hook...")
                await self.web_channel.C2_TERMINATE_ALL_CONNECTIONS()
            else:
                method = "C2_TERMINATE_ALL_CONNECTIONS"
                print(f"[C2 Hub Error] web_channel has no {method} method! It is still loading an old cache.")
            await runner.cleanup()
