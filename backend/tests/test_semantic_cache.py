"""G6: the semantic cache must never serve one user's answer to another user."""
import json
from typing import Any, Dict, List

import numpy as np
import pytest

from app.retrieval.embeddings import EmbeddingError
from app.services.caches.semantic_cache import SemanticCache, _cache_key
from tests.fakes import FakeRedis


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
SCOPE = "unassigned"  # Day 18: a chat outside any project, no instructions


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
    return SemanticCache(embedding_service=FakeEmbedder(), redis_client=redis_stub)


def test_query_cached_for_user_a_misses_for_user_b(cache: SemanticCache) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=3, mode="quick", scope_key=SCOPE)

    assert cache.lookup(QUERY, user_id=USER_B, user_doc_version=3, mode="quick", scope_key=SCOPE) is None


def test_users_at_doc_version_zero_stay_isolated(cache: SemanticCache) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE)

    assert cache.lookup(QUERY, user_id=USER_B, user_doc_version=0, mode="quick", scope_key=SCOPE) is None

    cache.store(QUERY, _answer("B"), user_id=USER_B, user_doc_version=0, mode="quick", scope_key=SCOPE)
    hit = cache.lookup(QUERY, user_id=USER_B, user_doc_version=0, mode="quick", scope_key=SCOPE)
    assert hit is not None
    assert hit["answer"] == "B's answer"


def test_same_user_same_scope_hits(cache: SemanticCache) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE)

    hit = cache.lookup(QUERY, user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE)
    assert hit is not None
    assert hit["answer"] == "A's answer"


def test_doc_version_zero_is_a_real_filter(cache: SemanticCache) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE)

    assert cache.lookup(QUERY, user_id=USER_A, user_doc_version=1, mode="quick", scope_key=SCOPE) is None


def test_different_mode_misses(cache: SemanticCache) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE)

    assert cache.lookup(QUERY, user_id=USER_A, user_doc_version=0, mode="detailed", scope_key=SCOPE) is None


def test_an_answer_from_one_scope_never_replays_in_another(cache: SemanticCache) -> None:
    # Day 18: the same user, the same question, the same doc_version, but project A's answer cites
    # project A's files; project B, a chat outside projects, and A with edited instructions all miss.
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick", scope_key="p:1")

    for other in ("p:2", SCOPE, "all", "p:1:iabc"):
        assert cache.lookup(QUERY, user_id=USER_A, user_doc_version=0, mode="quick", scope_key=other) is None, other
    assert cache.lookup(QUERY, user_id=USER_A, user_doc_version=0, mode="quick", scope_key="p:1") is not None


def test_entries_written_before_scopes_existed_never_match(cache: SemanticCache, redis_stub: FakeRedis) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE)
    entries = json.loads(redis_stub.store[_cache_key(USER_A)])
    for entry in entries:
        del entry["scope"]  # the shape stored before Day 18
    redis_stub.store[_cache_key(USER_A)] = json.dumps(entries)

    assert cache.lookup(QUERY, user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE) is None


def test_entries_are_stored_under_a_per_user_key(cache: SemanticCache, redis_stub: FakeRedis) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE)
    cache.store(QUERY, _answer("B"), user_id=USER_B, user_doc_version=0, mode="quick", scope_key=SCOPE)

    assert set(redis_stub.store) == {_cache_key(USER_A), _cache_key(USER_B)}


class FailingEmbedder:
    def embed_texts(self, texts: List[str]) -> np.ndarray:
        raise EmbeddingError("embedding text 1 of 1 failed: ClientError")


def test_a_failed_embedding_is_a_miss_on_lookup_and_a_no_op_on_store(redis_stub: FakeRedis) -> None:
    # Day 15: the cache is an optimization, so an embedding outage must not fail the chat.
    SemanticCache(embedding_service=FakeEmbedder(), redis_client=redis_stub).store(
        QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE
    )
    stored = dict(redis_stub.store)
    broken = SemanticCache(embedding_service=FailingEmbedder(), redis_client=redis_stub)  # type: ignore[arg-type]

    assert broken.lookup(QUERY, user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE) is None
    broken.store("another question", _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE)
    assert redis_stub.store == stored


def test_foreign_entry_under_a_users_key_is_ignored(cache: SemanticCache, redis_stub: FakeRedis) -> None:
    cache.store(QUERY, _answer("A"), user_id=USER_A, user_doc_version=0, mode="quick", scope_key=SCOPE)
    # Simulate a bug that writes user A's entries under user B's key.
    redis_stub.store[_cache_key(USER_B)] = redis_stub.store[_cache_key(USER_A)]

    assert cache.lookup(QUERY, user_id=USER_B, user_doc_version=0, mode="quick", scope_key=SCOPE) is None
