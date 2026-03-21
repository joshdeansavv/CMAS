"""Persistent memory system — cross-session, searchable knowledge store.

Unlike the Hub's key-value memory (project-scoped), this is a global knowledge base
that persists across projects and sessions. Agents can store and retrieve knowledge
by topic, with simple text-based search.
"""
from __future__ import annotations

import json
import time
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass


# Project root: src/cmas/core/memory.py -> parents[3] = project root
MEMORY_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "cmas_memory.db"


@dataclass
class MemoryEntry:
    id: int
    category: str       # e.g., "research", "analysis", "insight", "fact", "lesson"
    topic: str          # searchable topic/subject
    content: str        # the actual knowledge
    source: str         # which agent/project created this
    project: str        # which project this came from
    confidence: float   # 0.0-1.0, how reliable this knowledge is
    created_at: float
    accessed_at: float
    access_count: int


class Memory:
    """Global persistent knowledge store.

    Features:
    - Survives across projects and sessions
    - Searchable by topic, category, or free text
    - Tracks confidence and access frequency
    - Agents can store insights that other agents (even in future projects) can use
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else MEMORY_DB_PATH
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self.vector = None  # Optional VectorMemory instance, set externally
        self._init_db()

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT DEFAULT '',
                project TEXT DEFAULT '',
                confidence REAL DEFAULT 0.5,
                created_at REAL,
                accessed_at REAL,
                access_count INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_topic ON knowledge(topic);
            CREATE INDEX IF NOT EXISTS idx_category ON knowledge(category);

            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                what_happened TEXT NOT NULL,
                what_learned TEXT NOT NULL,
                applies_to TEXT DEFAULT '',
                project TEXT DEFAULT '',
                created_at REAL
            );
        """)
        self._conn.commit()

    # ── Store Knowledge ──────────────────────────────────────────

    def store(
        self,
        topic: str,
        content: str,
        category: str = "insight",
        source: str = "",
        project: str = "",
        confidence: float = 0.5,
    ) -> int:
        """Store a piece of knowledge. Returns the entry ID."""
        now = time.time()
        cursor = self._conn.execute(
            "INSERT INTO knowledge (category, topic, content, source, project, confidence, created_at, accessed_at, access_count) VALUES (?,?,?,?,?,?,?,?,?)",
            (category, topic, content, source, project, confidence, now, now, 0),
        )
        self._conn.commit()
        entry_id = cursor.lastrowid

        # Also store in vector DB for semantic search
        if self.vector:
            try:
                self.vector.store_knowledge(
                    doc_id=str(entry_id),
                    text=f"{topic}: {content}",
                    metadata={
                        "category": category, "source": source,
                        "project": project, "confidence": confidence,
                    },
                )
            except Exception:
                pass

        return entry_id

    # ── Retrieve Knowledge ───────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """Search knowledge by topic or content.

        Uses semantic (vector) search if available, falls back to text matching.
        """
        # Try semantic search first
        if self.vector:
            try:
                vector_results = self.vector.search_knowledge(query, n_results=limit)
                if vector_results:
                    entry_ids = [r["id"] for r in vector_results]
                    placeholders = ",".join("?" for _ in entry_ids)
                    rows = self._conn.execute(
                        f"SELECT * FROM knowledge WHERE id IN ({placeholders})",
                        entry_ids,
                    ).fetchall()
                    entries = []
                    for r in rows:
                        entry = MemoryEntry(**{k: r[k] for k in ["id", "category", "topic", "content", "source", "project", "confidence", "created_at", "accessed_at", "access_count"]})
                        entries.append(entry)
                        self._conn.execute(
                            "UPDATE knowledge SET accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
                            (time.time(), entry.id),
                        )
                    self._conn.commit()
                    if entries:
                        return entries
            except Exception:
                pass  # Fall through to text search

        # Fallback: text-based search
        rows = self._conn.execute(
            """SELECT *,
                CASE
                    WHEN topic LIKE ? THEN 2
                    WHEN content LIKE ? THEN 1
                    ELSE 0
                END as relevance
            FROM knowledge
            WHERE topic LIKE ? OR content LIKE ?
            ORDER BY relevance DESC, confidence DESC, accessed_at DESC
            LIMIT ?""",
            (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit),
        ).fetchall()

        entries = []
        for r in rows:
            entry = MemoryEntry(**{k: r[k] for k in ["id", "category", "topic", "content", "source", "project", "confidence", "created_at", "accessed_at", "access_count"]})
            entries.append(entry)
            self._conn.execute(
                "UPDATE knowledge SET accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
                (time.time(), entry.id),
            )
        self._conn.commit()
        return entries

    def get_by_topic(self, topic: str, limit: int = 10) -> List[MemoryEntry]:
        """Get knowledge entries for a specific topic."""
        return self.search(topic, limit=limit)

    def get_by_category(self, category: str, limit: int = 20) -> List[MemoryEntry]:
        """Get all knowledge in a category."""
        rows = self._conn.execute(
            "SELECT * FROM knowledge WHERE category = ? ORDER BY confidence DESC, accessed_at DESC LIMIT ?",
            (category, limit),
        ).fetchall()
        return [MemoryEntry(**{k: r[k] for k in ["id", "category", "topic", "content", "source", "project", "confidence", "created_at", "accessed_at", "access_count"]}) for r in rows]

    def get_recent(self, limit: int = 20) -> List[MemoryEntry]:
        """Get most recently accessed knowledge."""
        rows = self._conn.execute(
            "SELECT * FROM knowledge ORDER BY accessed_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [MemoryEntry(**{k: r[k] for k in ["id", "category", "topic", "content", "source", "project", "confidence", "created_at", "accessed_at", "access_count"]}) for r in rows]

    def update_confidence(self, entry_id: int, confidence: float):
        """Update confidence of a knowledge entry (e.g., after verification)."""
        self._conn.execute(
            "UPDATE knowledge SET confidence = ? WHERE id = ?", (confidence, entry_id)
        )
        self._conn.commit()

    def delete(self, entry_id: int):
        """Remove a knowledge entry."""
        self._conn.execute("DELETE FROM knowledge WHERE id = ?", (entry_id,))
        self._conn.commit()

    # ── Lessons Learned ──────────────────────────────────────────

    def store_lesson(self, what_happened: str, what_learned: str, applies_to: str = "", project: str = ""):
        """Store a lesson learned from experience (failures, corrections, insights)."""
        self._conn.execute(
            "INSERT INTO lessons (what_happened, what_learned, applies_to, project, created_at) VALUES (?,?,?,?,?)",
            (what_happened, what_learned, applies_to, project, time.time()),
        )
        self._conn.commit()

    def get_lessons(self, applies_to: str = "", limit: int = 10) -> List[Dict]:
        """Get relevant lessons learned."""
        if applies_to:
            rows = self._conn.execute(
                "SELECT * FROM lessons WHERE applies_to LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{applies_to}%", limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM lessons ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Summary ──────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Get memory statistics."""
        total = self._conn.execute("SELECT COUNT(*) as c FROM knowledge").fetchone()["c"]
        by_cat = self._conn.execute(
            "SELECT category, COUNT(*) as c FROM knowledge GROUP BY category"
        ).fetchall()
        lessons = self._conn.execute("SELECT COUNT(*) as c FROM lessons").fetchone()["c"]

        return {
            "total_entries": total,
            "by_category": {r["category"]: r["c"] for r in by_cat},
            "total_lessons": lessons,
        }

    def format_for_context(self, entries: List[MemoryEntry], max_chars: int = 3000) -> str:
        """Format memory entries into a string suitable for LLM context injection."""
        if not entries:
            return ""
        lines = ["RELEVANT KNOWLEDGE FROM MEMORY:"]
        chars = 0
        for e in entries:
            line = f"  [{e.category}] {e.topic}: {e.content} (confidence: {e.confidence:.1f})"
            if chars + len(line) > max_chars:
                break
            lines.append(line)
            chars += len(line)
        return "\n".join(lines)
