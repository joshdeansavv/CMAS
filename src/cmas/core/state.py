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
    PAUSED = "paused"
    KILLED = "killed"
    COMPLETED = "completed"


@dataclass
class Task:
    id: str
    description: str
    assigned_to: str = ""
    status: TaskStatus = TaskStatus.PENDING
    project_id: str = ""
    source_channel: str = "web"
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
        self.on_task_change = None
        self.on_message = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT,
                focus TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                description TEXT,
                assigned_to TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                project_id TEXT DEFAULT '',
                source_channel TEXT DEFAULT 'web',
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
                project_id TEXT DEFAULT '',
                source_channel TEXT DEFAULT 'web',
                updated_at REAL
            );

        """)
        conn.commit()

        # Migrations for existing DBs
        for migration in [
            "ALTER TABLE tasks ADD COLUMN source_channel TEXT DEFAULT 'web'",
            "ALTER TABLE agent_status ADD COLUMN project_id TEXT DEFAULT ''",
            "ALTER TABLE agent_status ADD COLUMN source_channel TEXT DEFAULT 'web'",
        ]:
            try:
                conn.execute(migration)
                conn.commit()
            except Exception:
                pass

    # ── Tasks ────────────────────────────────────────────────────

    def add_task(self, task: Task):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO tasks "
            "(id, description, assigned_to, status, project_id, source_channel, result, parent_task_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (task.id, task.description, task.assigned_to, task.status.value,
             task.project_id, task.source_channel, task.result,
             task.parent_task_id, task.created_at, task.updated_at),
        )
        conn.commit()
        if self.on_task_change:
            try:
                self.on_task_change(task.to_dict())
            except Exception:
                pass

    def update_task(self, task_id: str, **kwargs):
        conn = self._get_conn()
        kwargs["updated_at"] = time.time()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id]
        conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", vals)
        conn.commit()
        if self.on_task_change:
            try:
                task = self.get_task(task_id)
                if task:
                    self.on_task_change(task.to_dict())
            except Exception:
                pass

    def get_task(self, task_id: str) -> Optional[Task]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row:
            keys = row.keys()
            return Task(
                id=row["id"],
                description=row["description"],
                assigned_to=row["assigned_to"],
                status=TaskStatus(row["status"]),
                project_id=row["project_id"],
                source_channel=row["source_channel"] if "source_channel" in keys else "web",
                result=row["result"],
                parent_task_id=row["parent_task_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
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
        tasks = []
        for r in rows:
            keys = r.keys()
            tasks.append(Task(
                id=r["id"],
                description=r["description"],
                assigned_to=r["assigned_to"],
                status=TaskStatus(r["status"]) if r["status"] in TaskStatus._value2member_map_ else TaskStatus.FAILED,
                project_id=r["project_id"],
                source_channel=r["source_channel"] if "source_channel" in keys else "web",
                result=r["result"],
                parent_task_id=r["parent_task_id"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            ))
        return tasks

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
        if self.on_message:
            self.on_message(sender, recipient, content)

    def get_messages(self, recipient: str, since: float = 0) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM messages WHERE (recipient = ? OR recipient = 'SwarmChannel') AND timestamp > ? ORDER BY timestamp",
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

    def set_agent_status(self, name: str, status: str, current_task: str = "",
                         project_id: str = "", source_channel: str = "web"):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO agent_status "
            "(name, status, current_task, project_id, source_channel, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (name, status, current_task, project_id, source_channel, time.time()),
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

    # ── Projects ─────────────────────────────────────────────────
    def create_project(self, name: str, focus: str = "") -> str:
        import uuid
        pid = f"proj_{uuid.uuid4().hex[:6]}"
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO projects (id, name, focus, created_at) VALUES (?,?,?,?)",
            (pid, name, focus, time.time())
        )
        conn.commit()
        return pid

    def get_projects(self) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def rename_project(self, project_id: str, name: str):
        conn = self._get_conn()
        conn.execute("UPDATE projects SET name = ? WHERE id = ?", (name, project_id))
        conn.commit()

    def delete_project(self, project_id: str):
        """Delete a project and all its associated tasks and agent statuses."""
        conn = self._get_conn()
        conn.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM agent_status WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()

    def stop_project_tasks(self, project_id: str):
        """Mark all active tasks for a project as killed."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET status = 'killed', updated_at = ? WHERE project_id = ? AND status IN ('pending','in_progress')",
            (time.time(), project_id)
        )
        conn.execute(
            "UPDATE agent_status SET status = 'idle', current_task = '', updated_at = ? WHERE project_id = ?",
            (time.time(), project_id)
        )
        conn.commit()

    def get_project_tasks(self, project_id: str) -> List[Task]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM tasks WHERE project_id = ?", (project_id,)).fetchall()
        tasks = []
        for r in rows:
            keys = r.keys()
            tasks.append(Task(
                id=r["id"],
                description=r["description"],
                assigned_to=r["assigned_to"],
                status=TaskStatus(r["status"]) if r["status"] in TaskStatus._value2member_map_ else TaskStatus.FAILED,
                project_id=r["project_id"],
                source_channel=r["source_channel"] if "source_channel" in keys else "web",
                result=r["result"],
                parent_task_id=r["parent_task_id"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            ))
        return tasks

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
