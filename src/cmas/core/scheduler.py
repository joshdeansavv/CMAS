"""Background scheduler — reminders, cron jobs, and proactive behaviors."""
from __future__ import annotations

import asyncio
import json
import time
import sqlite3
from datetime import datetime
from typing import Any, Callable, Optional

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False


class Scheduler:
    """Background task runner that checks reminders, cron jobs, and runs proactive cycles.

    Runs as an asyncio task alongside the server in the same event loop.
    """

    def __init__(
        self,
        db_path: str,
        chat_handler: Any,
        memory: Any,
        config: Any,
        push_callback: Optional[Callable] = None,
    ):
        self.db_path = db_path
        self.chat_handler = chat_handler
        self.memory = memory
        self.config = config
        self.push_callback = push_callback
        self.proactive_interval = config.proactive_interval
        self._last_proactive = 0

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def run_forever(self):
        """Main background loop. Check every 30 seconds."""
        # Wait for server to fully start
        await asyncio.sleep(5)
        print("[Scheduler] Background scheduler running")

        while True:
            try:
                await self._check_reminders()
                await self._check_cron_jobs()

                # Proactive cycle on its own interval
                now = time.time()
                if now - self._last_proactive >= self.proactive_interval:
                    await self._proactive_cycle()
                    self._last_proactive = now

            except asyncio.CancelledError:
                print("[Scheduler] Shutting down")
                return
            except Exception as e:
                print(f"[Scheduler] Error in background loop: {e}")

            await asyncio.sleep(30)

    async def _check_reminders(self):
        """Fire any due reminders."""
        conn = self._conn()
        now = time.time()
        rows = conn.execute(
            "SELECT * FROM scheduled_jobs "
            "WHERE job_type = 'reminder' AND enabled = 1 AND next_run <= ?",
            (now,),
        ).fetchall()

        for row in rows:
            description = row["description"]
            session_id = row["session_id"]
            channel = row["channel"] or "web"

            msg = f"Reminder: {description}"
            await self._notify(session_id, channel, msg)

            # Disable one-time reminders
            conn.execute(
                "UPDATE scheduled_jobs SET enabled = 0, last_run = ? WHERE id = ?",
                (now, row["id"]),
            )
        conn.commit()
        conn.close()

    async def _check_cron_jobs(self):
        """Run any due cron jobs and schedule next run."""
        if not HAS_CRONITER:
            return

        conn = self._conn()
        now = time.time()
        rows = conn.execute(
            "SELECT * FROM scheduled_jobs "
            "WHERE job_type = 'cron' AND enabled = 1 AND next_run <= ?",
            (now,),
        ).fetchall()

        for row in rows:
            description = row["description"]
            cron_expr = row["schedule"]
            session_id = row["session_id"]
            channel = row["channel"] or "web"

            msg = f"Scheduled task: {description}"
            await self._notify(session_id, channel, msg)

            # Calculate next run
            try:
                next_run = croniter(cron_expr, datetime.now()).get_next(float)
            except Exception:
                next_run = now + 3600  # fallback: 1 hour

            conn.execute(
                "UPDATE scheduled_jobs SET last_run = ?, next_run = ? WHERE id = ?",
                (now, next_run, row["id"]),
            )
        conn.commit()
        conn.close()

    async def _proactive_cycle(self):
        """Proactive behaviors — run brain's DMN idle cycle for creative insights."""
        try:
            # Use brain's Default Mode Network if available
            from .brain import DefaultModeNetwork
            dmn = DefaultModeNetwork(memory=self.memory, model=self.config.model)
            results = await dmn.idle_cycle()

            # If we got interesting insights, we could store them
            # For now, just let the DMN run and store in memory
            recombinations = results.get("recombinations", [])
            
            gateway = getattr(self.chat_handler, "gateway", None)
            
            for r in recombinations:
                if r.get("content"):
                    self.memory.store(
                        topic=f"creative_insight",
                        content=r["content"][:500],
                        category="creative",
                        source="dmn_idle",
                        confidence=0.3,
                    )
                if gateway and r.get("connection"):
                    gateway._audit("DMN_Brain", "creative_insight", "memory_recombination", r.get("connection")[:100], "", True)
                    
            for e in results.get("exploration_insights", []):
                msg = e['query'][:100]
                if gateway:
                    gateway._audit("ExplorationAgent", "curiosity_gap", "web_search", msg, e['findings'][:100], True)

        except Exception as e:
            print(f"[Scheduler] DMN error: {e}")

    async def _notify(self, session_id: str, channel: str, message: str):
        """Send a notification to a user session."""
        if self.push_callback:
            try:
                await self.push_callback(session_id, channel, message)
            except Exception as e:
                print(f"[Scheduler] Push failed for {session_id}: {e}")
        else:
            print(f"[Scheduler] Notification (no push): {message}")
