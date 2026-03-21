"""Vector memory using ChromaDB for semantic search."""
from __future__ import annotations

from typing import List, Dict, Optional

try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


class VectorMemory:
    """Semantic search over knowledge and conversations using ChromaDB.

    Runs fully embedded — no external service needed.
    """

    def __init__(self, persist_dir: str = "./data/vectors"):
        if not HAS_CHROMADB:
            raise ImportError(
                "chromadb is required for vector memory: pip install chromadb"
            )
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.knowledge = self.client.get_or_create_collection(
            name="knowledge",
            metadata={"hnsw:space": "cosine"},
        )
        self.conversations = self.client.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"},
        )

    # ── Knowledge ─────────────────────────────────────────────────

    def store_knowledge(self, doc_id: str, text: str, metadata: Optional[Dict] = None):
        """Store a knowledge entry for semantic search."""
        self.knowledge.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )

    def search_knowledge(self, query: str, n_results: int = 5,
                         where: Optional[Dict] = None) -> List[Dict]:
        """Semantic search over knowledge entries."""
        kwargs = {"query_texts": [query], "n_results": n_results}
        if where:
            kwargs["where"] = where
        try:
            results = self.knowledge.query(**kwargs)
        except Exception:
            return []
        return self._format_results(results)

    # ── Conversations ─────────────────────────────────────────────

    def store_conversation(self, doc_id: str, text: str, metadata: Optional[Dict] = None):
        """Store a conversation turn for semantic search."""
        self.conversations.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )

    def search_conversations(self, query: str, n_results: int = 5,
                             session_id: Optional[str] = None) -> List[Dict]:
        """Semantic search over past conversations."""
        kwargs = {"query_texts": [query], "n_results": n_results}
        if session_id:
            kwargs["where"] = {"session_id": session_id}
        try:
            results = self.conversations.query(**kwargs)
        except Exception:
            return []
        return self._format_results(results)

    # ── Helpers ───────────────────────────────────────────────────

    def _format_results(self, results: dict) -> List[Dict]:
        """Convert ChromaDB results to list of dicts."""
        out = []
        if not results or not results.get("ids"):
            return out
        ids = results["ids"][0]
        docs = results["documents"][0] if results.get("documents") else [""] * len(ids)
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
        dists = results["distances"][0] if results.get("distances") else [0] * len(ids)
        for i, doc_id in enumerate(ids):
            out.append({
                "id": doc_id,
                "text": docs[i],
                "metadata": metas[i],
                "distance": dists[i],
            })
        return out

    def get_stats(self) -> Dict:
        return {
            "knowledge_count": self.knowledge.count(),
            "conversation_count": self.conversations.count(),
        }
