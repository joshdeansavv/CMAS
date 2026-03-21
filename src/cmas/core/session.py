"""Session and conversation history manager."""
from __future__ import annotations

import json
import time
import sqlite3
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Session:
    session_id: str
    user_id: str
    channel: str = "web"
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    context_summary: str = ""


class SessionManager:
    """Manages sessions and conversation history in SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
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

    # ── Sessions ──────────────────────────────────────────────────

    def get_or_create(self, session_id: str, user_id: str, channel: str = "web") -> Session:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE sessions SET last_active = ? WHERE session_id = ?",
                (time.time(), session_id),
            )
            conn.commit()
            return Session(
                session_id=row["session_id"],
                user_id=row["user_id"],
                channel=row["channel"],
                created_at=row["created_at"],
                last_active=time.time(),
                context_summary=row["context_summary"] or "",
            )
        now = time.time()
        conn.execute(
            "INSERT INTO sessions (session_id, user_id, channel, created_at, last_active) VALUES (?,?,?,?,?)",
            (session_id, user_id, channel, now, now),
        )
        conn.commit()
        return Session(session_id=session_id, user_id=user_id, channel=channel,
                       created_at=now, last_active=now)

    def update_summary(self, session_id: str, summary: str):
        conn = self._conn()
        conn.execute(
            "UPDATE sessions SET context_summary = ? WHERE session_id = ?",
            (summary, session_id),
        )
        conn.commit()

    def list_sessions(self, user_id: Optional[str] = None, limit: int = 20) -> List[Session]:
        conn = self._conn()
        if user_id:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE user_id = ? ORDER BY last_active DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY last_active DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [Session(**{k: r[k] for k in r.keys()}) for r in rows]

    # ── Conversation History ──────────────────────────────────────

    def add_message(self, session_id: str, user_id: str, role: str,
                    content: str, channel: str = "web", metadata: Optional[Dict] = None):
        conn = self._conn()
        conn.execute(
            "INSERT INTO conversations (session_id, user_id, channel, role, content, timestamp, metadata) "
            "VALUES (?,?,?,?,?,?,?)",
            (session_id, user_id, channel, role, content, time.time(),
             json.dumps(metadata or {})),
        )
        conn.commit()

    def get_context(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Get recent messages formatted for LLM context."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE session_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        # Reverse to chronological order
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def get_full_history(self, session_id: str, limit: int = 500) -> List[Dict]:
        """Get full history with metadata."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM conversations WHERE session_id = ? ORDER BY timestamp LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_history(self, session_id: str, query: str, limit: int = 10) -> List[Dict]:
        """Simple text search across conversation history."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT role, content, timestamp FROM conversations "
            "WHERE session_id = ? AND content LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (session_id, f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_messages(self, session_id: str) -> int:
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM conversations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["c"]
