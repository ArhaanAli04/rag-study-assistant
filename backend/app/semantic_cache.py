#semantic cache index so that similar queries can resue previous answers
import json
import os
from typing import List, Optional, Dict, Any
from app.core.logging import setup_logging
logger = setup_logging()

import numpy as np
import redis

from app.index_builder import IndexBuilder  # to reuse same embedding model

SEM_CACHE_KEY_PREFIX = "semantic_cache"
DEFAULT_SEMANTIC_CACHE_REDIS_URL = "redis://localhost:6379/1"


def semantic_cache_redis_url() -> str:
    # A dedicated setting lets the semantic cache live in its own Redis DB, so flushing the
    # query/web caches in REDIS_URL's DB doesn't wipe it. Falling back to REDIS_URL keeps
    # deployments that set only REDIS_URL (Render today) on their current DB.
    return (
        os.getenv("SEMANTIC_CACHE_REDIS_URL")
        or os.getenv("REDIS_URL")
        or DEFAULT_SEMANTIC_CACHE_REDIS_URL
    )


def _cache_key(user_id: int) -> str:
    # One Redis key per user makes cross-user reads impossible by construction and
    # gives each user their own eviction budget (G6).
    return f"{SEM_CACHE_KEY_PREFIX}:{user_id}"


def _to_json_safe(obj):
    """
    Recursively convert numpy / non-serializable types into plain Python
    so json.dumps works.
    """
    import numpy as np

    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_json_safe(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_to_json_safe(v) for v in obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    return obj

class SemanticCache:
    """
    Very simple semantic cache stored as one list per user in Redis.
    Not production-grade, but enough to demonstrate the idea.
    """

    def __init__(self, index_builder: IndexBuilder, redis_client: Optional[redis.Redis] = None):
        self.r = redis_client if redis_client is not None else redis.from_url(semantic_cache_redis_url())
        self.index_builder = index_builder

    def _load_entries(self, user_id: int) -> List[Dict[str, Any]]:
        val = self.r.get(_cache_key(user_id))
        if not val:
            return []
        try:
            return json.loads(val)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Semantic cache for user %s is corrupt; ignoring it", user_id)
            return []

    def _save_entries(self, user_id: int, entries: List[Dict[str, Any]]) -> None:
        safe_entries = _to_json_safe(entries)
        self.r.set(_cache_key(user_id), json.dumps(safe_entries))

    def clear_user(self, user_id: int) -> None:
        """Drop every cached answer of ``user_id`` (account deletion; ids can be reused)."""
        self.r.delete(_cache_key(user_id))

    def lookup(
        self,
        query: str,
        user_id: int,
        user_doc_version: int,
        mode: str,
        threshold: float = 0.92,
    ) -> Optional[Dict[str, Any]]:
        entries = self._load_entries(user_id)
        # The user_id check is a backstop in case an entry ever lands under the wrong key.
        # doc_version is compared exactly: version 0 is a real version, not "no filter".
        relevant_entries = [e for e in entries
                            if e.get("user_id") == user_id
                            and e.get("doc_version") == user_doc_version
                            and e.get("mode") == mode]

        if not relevant_entries:
            return None

        q_emb = np.array(self.index_builder.embed_texts([query])[0])
        best_sim = -1.0
        best_entry = None
        for e in relevant_entries:
            emb = np.array(e["embedding"])
            # cosine similarity
            num = float(np.dot(q_emb, emb))
            denom = float(np.linalg.norm(q_emb) * np.linalg.norm(emb) + 1e-8)
            sim = num / denom
            if sim > best_sim:
                best_sim = sim
                best_entry = e
        if best_sim >= threshold:
            logger.info("CACHE HIT: user_id=%s query='%s', score=%.3f, mode=%s", user_id, query[:50], best_sim, mode)
            return best_entry["value"]
        logger.info("CACHE MISS: user_id=%s query='%s', mode=%s", user_id, query[:50], mode)
        return None


    def store(
        self,
        query: str,
        value: Dict[str, Any],
        user_id: int,
        user_doc_version: int,
        mode: str,
        max_entries: int = 64,
    ) -> None:
        q_emb = self.index_builder.embed_texts([query])[0]
        entries = self._load_entries(user_id)
        safe_value = _to_json_safe(value)

        safe_value["doc_version"] = user_doc_version
        safe_value["mode"] = mode
        entries.append({
            "query": query,
            "embedding": list(map(float, q_emb)),
            "value": safe_value,
            "user_id": user_id,
            "doc_version": user_doc_version,
            "mode": mode,
        })
        if len(entries) > max_entries:
            entries = entries[-max_entries:]
        self._save_entries(user_id, entries)
