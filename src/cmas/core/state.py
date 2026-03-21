"""Shared state, memory, and communication hub for the multi-agent system."""
from __future__ import annotations

import json
import time
import sqlite3
import threading
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, field, asdict
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Task:
    id: str
    description: str
    assigned_to: str = ""
    status: TaskStatus = TaskStatus.PENDING
    result: str = ""
    parent_task_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self):
        d = asdict(self)
        d["status"] = self.status.value
        return d


class Hub:
    """Central communication and state hub. Thread-safe via SQLite."""

    def __init__(self, project_dir):
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.project_dir / "hub.db"
        self._local = threading.local()
        self.on_status_change = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                description TEXT,
                assigned_to TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                result TEXT DEFAULT '',
                parent_task_id TEXT DEFAULT '',
                created_at REAL,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                recipient TEXT,
                content TEXT,
                timestamp REAL
            );
            CREATE TABLE IF NOT EXISTS memory (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS agent_status (
                name TEXT PRIMARY KEY,
                status TEXT DEFAULT 'idle',
                current_task TEXT DEFAULT '',
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'web',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL,
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_conv_session
                ON conversations(session_id, timestamp);

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'web',
                created_at REAL,
                last_active REAL,
                context_summary TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                schedule TEXT NOT NULL,
                action TEXT NOT NULL DEFAULT '{}',
                session_id TEXT,
                user_id TEXT DEFAULT '',
                channel TEXT DEFAULT 'web',
                enabled INTEGER DEFAULT 1,
                last_run REAL DEFAULT 0,
                next_run REAL,
                created_at REAL
            );
        """)
        conn.commit()

    # ── Tasks ────────────────────────────────────────────────────

    def add_task(self, task: Task):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?,?)",
            (task.id, task.description, task.assigned_to, task.status.value,
             task.result, task.parent_task_id, task.created_at, task.updated_at),
        )
        conn.commit()

    def update_task(self, task_id: str, **kwargs):
        conn = self._get_conn()
        kwargs["updated_at"] = time.time()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id]
        conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", vals)
        conn.commit()

    def get_task(self, task_id: str) -> Optional[Task]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row:
            return Task(**{k: row[k] for k in row.keys()})
        return None

    def get_tasks(self, status: Optional[str] = None, assigned_to: Optional[str] = None) -> List[Task]:
        conn = self._get_conn()
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if assigned_to:
            query += " AND assigned_to = ?"
            params.append(assigned_to)
        query += " ORDER BY created_at"
        rows = conn.execute(query, params).fetchall()
        return [Task(**{k: r[k] for k in r.keys()}) for r in rows]

    def get_all_tasks(self) -> List[Task]:
        return self.get_tasks()

    # ── Messages ─────────────────────────────────────────────────

    def send_message(self, sender: str, recipient: str, content: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO messages (sender, recipient, content, timestamp) VALUES (?,?,?,?)",
            (sender, recipient, content, time.time()),
        )
        conn.commit()

    def get_messages(self, recipient: str, since: float = 0) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM messages WHERE recipient = ? AND timestamp > ? ORDER BY timestamp",
            (recipient, since),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_messages(self, limit: int = 50) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Memory (key-value) ───────────────────────────────────────

    def remember(self, key: str, value: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO memory (key, value, updated_at) VALUES (?,?,?)",
            (key, value, time.time()),
        )
        conn.commit()

    def recall(self, key: str) -> Optional[str]:
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM memory WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def recall_all(self) -> Dict[str, str]:
        conn = self._get_conn()
        rows = conn.execute("SELECT key, value FROM memory").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ── Agent Status ─────────────────────────────────────────────

    def set_agent_status(self, name: str, status: str, current_task: str = ""):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO agent_status (name, status, current_task, updated_at) VALUES (?,?,?,?)",
            (name, status, current_task, time.time()),
        )
        conn.commit()
        if self.on_status_change:
            try:
                self.on_status_change(name, status, current_task)
            except Exception:
                pass

    def get_agent_statuses(self) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM agent_status ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    # ── Summary ──────────────────────────────────────────────────

    def get_status_summary(self) -> str:
        tasks = self.get_all_tasks()
        agents = self.get_agent_statuses()

        lines = ["=== System Status ==="]
        lines.append(f"\nAgents ({len(agents)}):")
        for a in agents:
            lines.append(f"  {a['name']}: {a['status']} | task: {a['current_task']}")

        by_status = {}
        for t in tasks:
            by_status.setdefault(t.status, []).append(t)

        lines.append(f"\nTasks ({len(tasks)}):")
        for status in ["in_progress", "pending", "done", "failed"]:
            group = by_status.get(status, [])
            if group:
                lines.append(f"  [{status}] ({len(group)}):")
                for t in group[:10]:
                    assignee = f" -> {t.assigned_to}" if t.assigned_to else ""
                    lines.append(f"    {t.id}: {t.description[:80]}{assignee}")

        return "\n".join(lines)
