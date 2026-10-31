"""G6: the semantic cache must never serve one user's answer to another user."""
import os
import sys
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from semantic_cache import SemanticCache, _cache_key


class FakeRedis:
    """Only the get/set calls SemanticCache makes, with bytes values like redis-py."""

    def __init__(self) -> None:
        self.store: Dict[str, bytes] = {}

    def get(self, key: str) -> Optional[bytes]:
        return self.store.get(key)

    def set(self, key: str, value: str) -> None:
        self.store[key] = value.encode("utf-8")


class FakeEmbedder:
    """One-hot vector per distinct text: identical queries score 1.0, different ones 0.0."""

    def __init__(self, dim: int = 32) -> None:
        self.dim = dim
        self.vocab: Dict[str, int] = {}

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            out[i, self.vocab.setdefault(text, len(self.vocab))] = 1.0
        return out


QUERY = "summarize chapter 2"
USER_A = 1
USER_B = 2


def _answer(owner: str) -> Dict[str, Any]:
    return {
        "answer": f"{owner}'s answer",
        "sources": [{"file_name": f"{owner}_thesis.pdf", "text": f"{owner}'s private text"}],
    }


@pytest.fixture
def redis_stub() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def cache(redis_stub: FakeRedis) -> SemanticCache:
    return SemanticCache(index_builder=FakeEmbedder(), redis_client=redis_stub)


def test_query_cached_for_user_a_misses_for_user_b(cache: SemanticCache) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=3, mode="quick")

    assert cache.lookup(QUERY, user_id=USER_B, user_doc_version=3, mode="quick") is None


def test_users_at_doc_version_zero_stay_isolated(cache: SemanticCache) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick")

    assert cache.lookup(QUERY, user_id=USER_B, user_doc_version=0, mode="quick") is None

    cache.store(QUERY, _answer("B"), user_id=USER_B, user_doc_version=0, mode="quick")
    hit = cache.lookup(QUERY, user_id=USER_B, user_doc_version=0, mode="quick")
    assert hit is not None
    assert hit["answer"] == "B's answer"


def test_same_user_same_scope_hits(cache: SemanticCache) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick")

    hit = cache.lookup(QUERY, user_id=USER_A, user_doc_version=0, mode="quick")
    assert hit is not None
    assert hit["answer"] == "A's answer"


def test_doc_version_zero_is_a_real_filter(cache: SemanticCache) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick")

    assert cache.lookup(QUERY, user_id=USER_A, user_doc_version=1, mode="quick") is None


def test_different_mode_misses(cache: SemanticCache) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick")

    assert cache.lookup(QUERY, user_id=USER_A, user_doc_version=0, mode="detailed") is None


def test_entries_are_stored_under_a_per_user_key(cache: SemanticCache, redis_stub: FakeRedis) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick")
    cache.store(QUERY, _answer("B"), user_id=USER_B, user_doc_version=0, mode="quick")

    assert set(redis_stub.store) == {_cache_key(USER_A), _cache_key(USER_B)}


def test_foreign_entry_under_a_users_key_is_ignored(cache: SemanticCache, redis_stub: FakeRedis) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick")
    # Simulate a bug that writes user A's entries under user B's key.
    redis_stub.store[_cache_key(USER_B)] = redis_stub.store[_cache_key(USER_A)]

    assert cache.lookup(QUERY, user_id=USER_B, user_doc_version=0, mode="quick") is None
