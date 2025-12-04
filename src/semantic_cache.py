#semantic cache index so that similar queries can resue previous answers
import json
import os
from typing import List, Optional, Dict, Any
from logger import setup_logging
logger = setup_logging()

import numpy as np
import redis

from index_builder import IndexBuilder  # to reuse same embedding model

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/1")  # separate DB for semantic cache
SEM_CACHE_KEY = "semantic_cache_entries"

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
    Very simple semantic cache stored as a list in Redis.
    Not production-grade, but enough to demonstrate the idea.
    """

    def __init__(self, index_builder: IndexBuilder):
        self.r = redis.from_url(REDIS_URL)
        self.index_builder = index_builder
        # TEMP: clear old bad entries once
        

    def _load_entries(self) -> List[Dict[str, Any]]:
        val = self.r.get(SEM_CACHE_KEY)
        if not val:
            return []
        try:
            return json.loads(val)
        except Exception:
            return []

    def _save_entries(self, entries: List[Dict[str, Any]]):
        safe_entries = _to_json_safe(entries)
        self.r.set(SEM_CACHE_KEY, json.dumps(safe_entries))

    def lookup(self, query: str, threshold: float = 0.92, user_doc_version: Optional[int] = None,mode: Optional[str] = None) -> Optional[Dict[str, Any]]:
        entries = self._load_entries()
        relevant_entries = [e for e in entries 
                       if (not user_doc_version or e.get("doc_version") == user_doc_version)
                       and (not mode or e.get("mode") == mode)]
        
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
            logger.info("CACHE HIT: query='%s', score=%.3f, mode=%s", query[:50], best_sim, mode)
            return best_entry["value"]
        logger.info("CACHE MISS: query='%s', mode=%s", query[:50], mode)
        return None


    def store(self, query: str, value: Dict[str, Any], user_doc_version: int,mode: str, max_entries: int = 64):
        q_emb = self.index_builder.embed_texts([query])[0]
        entries = self._load_entries()
        safe_value = _to_json_safe(value)
        
        # ADD doc_version to both value and entry metadata
        safe_value["doc_version"] = user_doc_version
        safe_value["mode"] = mode  # ADD MODE TO STORED VALUE
        entries.append({
            "query": query, 
            "embedding": list(map(float, q_emb)), 
            "value": safe_value,
            "doc_version": user_doc_version,  # NEW: store version with entry
            "mode": mode,  # NEW: store mode with entry
        })
        if len(entries) > max_entries:
            entries = entries[-max_entries:]
        self._save_entries(entries)
