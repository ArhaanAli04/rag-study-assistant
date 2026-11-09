"""On-disk embedding cache for the eval only (Decision 5A).

Every eval run re-indexes the corpus because nothing persists (I4); with one Gemini call per text
(I3) that is ~250 calls a run. Cached vectors make later runs free and reproducible.
"""
import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from google import genai

from app.retrieval.embeddings import EmbeddingService
from eval.retrieval.rate_limit import RateLimiter, estimate_tokens

DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent / ".cache" / "embeddings.sqlite"


class EmbeddingFailure(RuntimeError):
    """EmbeddingService turns API errors into zero vectors; caching one would poison every later
    run, and indexing one would silently corrupt the eval, so the run stops instead."""


class CachedEmbeddingService(EmbeddingService):
    def __init__(
        self, client: genai.Client, cache_path: Path = DEFAULT_CACHE_PATH, limiter: Optional[RateLimiter] = None
    ) -> None:
        super().__init__(client)
        self.limiter = limiter
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(cache_path))
        self._db.execute("CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector BLOB NOT NULL)")
        self.hits = 0
        self.api_calls = 0
        self.blank_texts = 0

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model_name}|{self.dimension}|{text}".encode("utf-8")).hexdigest()

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)

        keys = [self._key(t) for t in texts]
        found: Dict[str, np.ndarray] = {}
        # The API rejects empty content (400), and production's EmbeddingService then indexes a zero
        # vector. The PPTX chunker emits a few empty chunks (3 in the Day 11 corpus), so the eval
        # indexes the same zero vector without spending a request on a certain 400.
        for key, text in zip(keys, texts):
            if not text.strip() and key not in found:
                found[key] = np.zeros(self.dimension, dtype=np.float32)
                self.blank_texts += 1
        for key in set(keys) - set(found):
            row = self._db.execute("SELECT vector FROM embeddings WHERE key = ?", (key,)).fetchone()
            if row is not None:
                found[key] = np.frombuffer(row[0], dtype=np.float32)

        missing = [(key, text) for key, text in zip(keys, texts) if key not in found]
        unique_missing = list(dict(missing).items())
        self.hits += len(texts) - len(missing)

        # One text per request, each paced and committed on its own, so a run stopped by a 429 or
        # the daily limit keeps every vector it paid for and resumes from the cache.
        for key, text in unique_missing:
            if self.limiter is not None:
                self.limiter.acquire(estimate_tokens(text))
            self.api_calls += 1
            vector = super().embed_texts([text])[0]
            if not np.any(vector):
                raise EmbeddingFailure(
                    f"embedding call failed after {self.api_calls - 1} successful calls this run (zero vector; "
                    "a 429 here may be the daily limit). Cached vectors are kept: re-run to resume."
                )
            found[key] = vector.astype(np.float32)
            self._db.execute("INSERT OR REPLACE INTO embeddings (key, vector) VALUES (?, ?)", (key, found[key].tobytes()))
            self._db.commit()

        return np.stack([found[key] for key in keys])

    def close(self) -> None:
        self._db.close()
