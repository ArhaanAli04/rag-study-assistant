"""Offline stand-ins for the external systems the backend talks to (Gemini, Redis).

They replace the clients at the SDK boundary, so all of the app's own code above them —
prompt building, JSON parsing, SSE framing, caching, DB writes — still runs in tests.
"""
import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterator, List, Optional, Union

import numpy as np
from google.genai import errors as genai_errors

FAKE_EMBEDDING_DIM = 768
DEFAULT_REPLY = "Computer Science"
DEFAULT_STREAM = ["Photosynthesis turns light ", "into chemical energy."]


class FakeRedis:
    """In-memory Redis with the calls the app makes (get / set / setex / delete), bytes values like redis-py."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.store: Dict[str, bytes] = {}
        self.ttls: Dict[str, int] = {}

    def get(self, key: str) -> Optional[bytes]:
        return self.store.get(key)

    def set(self, key: str, value: Union[str, bytes]) -> bool:
        self.store[key] = value.encode("utf-8") if isinstance(value, str) else value
        return True

    def setex(self, key: str, ttl_seconds: int, value: Union[str, bytes]) -> bool:
        self.ttls[key] = ttl_seconds
        return self.set(key, value)

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                removed += 1
            self.ttls.pop(key, None)
        return removed

    def flushall(self) -> None:
        self.store.clear()
        self.ttls.clear()

    def close(self) -> None:
        """The app closes its clients at shutdown; the shared in-memory store survives it."""


class FakeRedisServer:
    """One shared FakeRedis behind every way the app builds a client.

    Sharing one store mirrors production closely enough: the query and web caches share DB 0,
    and the semantic cache's keys never collide with theirs.
    """

    def __init__(self) -> None:
        self.db = FakeRedis()

    def from_url(self, url: str, *args: Any, **kwargs: Any) -> FakeRedis:
        return self.db

    def client_class(self, *args: Any, **kwargs: Any) -> FakeRedis:
        return self.db


def fake_embedding(text: str, dim: int = FAKE_EMBEDDING_DIM) -> List[float]:
    """Unit vector seeded by the text's hash: identical text → identical vector on every run."""
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
    vector = np.random.default_rng(seed).standard_normal(dim)
    return (vector / np.linalg.norm(vector)).tolist()


@dataclass
class _Embedding:
    values: List[float]


@dataclass
class _EmbedResponse:
    embeddings: List[_Embedding]


@dataclass
class _TextResponse:
    text: str


@dataclass
class FakeGemini:
    """The scripting handle tests use; shared by every FakeGenaiClient the app constructs.

    Queue replies with `replies` / `streams` for one test; when a queue is empty the default is used.
    """

    replies: Deque[str] = field(default_factory=deque)
    streams: Deque[List[str]] = field(default_factory=deque)
    default_reply: str = DEFAULT_REPLY
    default_stream: List[str] = field(default_factory=lambda: list(DEFAULT_STREAM))
    prompts: List[Any] = field(default_factory=list)
    embed_calls: int = 0
    stream_calls: int = 0
    # Fail the Nth embed call from now on (1 = the next one), like a 429 mid-upload; None = never.
    fail_embedding_at: Optional[int] = None

    def reset(self) -> None:
        self.replies.clear()
        self.streams.clear()
        self.prompts.clear()
        self.embed_calls = 0
        self.stream_calls = 0
        self.fail_embedding_at = None


class _FakeModels:
    def __init__(self, gemini: FakeGemini) -> None:
        self._gemini = gemini

    def embed_content(self, model: str, contents: Any, config: Any = None, **kwargs: Any) -> _EmbedResponse:
        self._gemini.embed_calls += 1
        if self._gemini.fail_embedding_at is not None:
            self._gemini.fail_embedding_at -= 1
            if self._gemini.fail_embedding_at == 0:
                self._gemini.fail_embedding_at = None
                raise genai_errors.ClientError(429, {"error": {"code": 429, "message": "fake quota exhausted"}})
        texts = contents if isinstance(contents, list) else [contents]
        # Like the real API: the requested size wins, so the app's EMBEDDING_DIM contract is exercised.
        dim = getattr(config, "output_dimensionality", None) or FAKE_EMBEDDING_DIM
        return _EmbedResponse([_Embedding(fake_embedding(str(t), dim)) for t in texts])

    def generate_content(self, model: str, contents: Any, **kwargs: Any) -> _TextResponse:
        self._gemini.prompts.append(contents)
        reply = self._gemini.replies.popleft() if self._gemini.replies else self._gemini.default_reply
        return _TextResponse(reply)

    def generate_content_stream(self, model: str, contents: Any, **kwargs: Any) -> Iterator[_TextResponse]:
        self._gemini.prompts.append(contents)
        self._gemini.stream_calls += 1
        pieces =self._gemini.streams.popleft() if self._gemini.streams else self._gemini.default_stream
        return iter([_TextResponse(p) for p in pieces])


class FakeEmbedder:
    """Any vector will do for retrieval unit tests whose candidates come from FakeChunkSearch."""

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        return np.ones((len(texts), 2), dtype=np.float32) / np.sqrt(2)


class FakeChunkSearch:
    """Scripted candidate lists for RetrievalService unit tests (no database); counts searches."""

    def __init__(self, vector: Optional[List[Dict[str, Any]]] = None, keyword: Optional[List[Dict[str, Any]]] = None) -> None:
        self.vector = vector or []
        self.keyword = keyword or []
        self.searches = 0

    def search(self, query_embedding: np.ndarray, keyword_query: str, user_id: str, top_k: int) -> Any:
        from app.retrieval.pg_chunk_search import Candidates

        self.searches += 1
        # Fresh dicts per call: hybrid_retrieve annotates metadata in place.
        return Candidates(
            vector=[{**r, "metadata": dict(r["metadata"])} for r in self.vector[:top_k]],
            keyword=[{**r, "metadata": dict(r["metadata"])} for r in self.keyword[:top_k]],
        )

    def vector_only(
        self, query_embedding: np.ndarray, user_id: str, top_k: int, metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        return self.vector[:top_k]


class FakeTavilyClient:
    """Drop-in for tavily.TavilyClient. Web search stays off unless a test sets TAVILY_API_KEY,
    because WebSearchClient refuses to build a client without one."""

    results: List[Dict[str, str]] = []
    queries: List[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def search(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        FakeTavilyClient.queries.append(query)
        return {"results": list(FakeTavilyClient.results)}


class FakeGenaiClient:
    """Drop-in for google.genai.Client; every instance shares one FakeGemini script."""

    gemini: FakeGemini = FakeGemini()
    instances: int = 0  # constructions so far; each real one costs ~3 s, so the app builds one

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        FakeGenaiClient.instances += 1
        self.models = _FakeModels(FakeGenaiClient.gemini)
