"""E4 needs retrieval with web search and the L1 cache off, and with chosen fusion weights; the
defaults must stay what production has always run."""
from typing import Any

import pytest

from app.retrieval.context_assembly import assemble_context
from app.retrieval.context_compressor import SimpleContextCompressor
from app.retrieval.query_decomposer import QueryDecomposer
from app.retrieval.retrieval_service import RetrievalService
from app.services.caches.query_cache import QueryCache
from app.services.caches.web_cache import WebCache
from tests.fakes import FakeChunkSearch, FakeEmbedder, FakeRedis

QUERY = "explain photosynthesis chlorophyll"
TEXT = "Photosynthesis uses chlorophyll to turn light into chemical energy."


def counting_search() -> FakeChunkSearch:
    return FakeChunkSearch(vector=[
        {"score": 0.9 - i * 0.1, "text": TEXT, "metadata": {"file_name": "notes.pdf", "chunk_index": i}}
        for i in range(3)
    ])


def _service(chunk_search: FakeChunkSearch, **switches: Any) -> RetrievalService:
    redis_stub = FakeRedis()
    return RetrievalService(
        embedding_service=FakeEmbedder(),
        chunk_search=chunk_search,
        query_cache=QueryCache(redis_stub),  # type: ignore[arg-type]
        web_cache=WebCache(redis_stub),  # type: ignore[arg-type]
        **switches,
    )


def test_defaults_are_production_behaviour() -> None:
    service = _service(counting_search())

    assert service.web_search_enabled is True
    assert service.l1_cache_enabled is True
    assert (service.vector_weight, service.keyword_weight) == (0.6, 0.4)


def test_web_search_off_never_calls_the_web(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(counting_search(), web_search_enabled=False)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("web search was called")

    monkeypatch.setattr(service, "get_web_chunks", fail)
    result = service.hybrid_retrieve(QUERY, user_id="1", doc_version=0, top_k=5)

    assert result["web_results"] == []
    assert all(r["metadata"]["source_type"] == "local" for r in result["results"])


def test_l1_cache_off_recomputes_a_repeated_query() -> None:
    chunk_search = counting_search()
    service = _service(chunk_search, web_search_enabled=False, l1_cache_enabled=False)

    first = service.hybrid_retrieve(QUERY, user_id="1", doc_version=0, top_k=5)
    second = service.hybrid_retrieve(QUERY, user_id="1", doc_version=0, top_k=5)

    assert chunk_search.searches == 2
    assert "from_l1_cache" not in second
    assert service.l1_cache_lookup("1", QUERY, 0) is None
    assert first["results"] == second["results"]


def test_l1_cache_on_replays_a_repeated_query() -> None:
    chunk_search = counting_search()
    service = _service(chunk_search, web_search_enabled=False)

    service.hybrid_retrieve(QUERY, user_id="1", doc_version=0, top_k=5)
    second = service.hybrid_retrieve(QUERY, user_id="1", doc_version=0, top_k=5)

    assert chunk_search.searches == 1
    assert second["from_l1_cache"] is True


def test_one_search_call_per_retrieval_returns_both_halves() -> None:
    # CO6: vector and keyword candidates come from one ChunkSearch.search, i.e. one DB session.
    keyword_only = {"score": 2.0, "text": TEXT, "metadata": {"file_name": "notes.pdf", "chunk_index": 9}}
    chunk_search = FakeChunkSearch(vector=counting_search().vector, keyword=[keyword_only])
    service = _service(chunk_search, web_search_enabled=False, l1_cache_enabled=False)

    result = service.hybrid_retrieve(QUERY, user_id="1", doc_version=0, top_k=5)

    assert chunk_search.searches == 1
    assert 9 in {c["metadata"]["chunk_index"] for c in result["all_candidates"]}


def test_fusion_weights_are_applied() -> None:
    # Only the vector half has results, so the best hybrid score is exactly the vector weight.
    service = _service(counting_search(), web_search_enabled=False, vector_weight=1.0, keyword_weight=0.0)

    result = service.hybrid_retrieve(QUERY, user_id="1", doc_version=0, top_k=5)

    assert result["results"][0]["score"] == pytest.approx(1.0)


def test_assemble_context_matches_the_retrieval_result() -> None:
    service = _service(counting_search(), web_search_enabled=False, l1_cache_enabled=False)
    direct = service.hybrid_retrieve(QUERY, user_id="1", doc_version=0, top_k=5)

    context = assemble_context(
        service, QueryDecomposer(), SimpleContextCompressor(),
        query=QUERY, user_id="1", doc_version=0, top_k=5,
    )

    assert context.sub_queries == [QUERY]
    assert context.confidence == pytest.approx(direct["confidence"])
    # Below WEB_FALLBACK_BELOW the flag is set even with web search off; it records the decision.
    assert context.fallback_used is direct["fallback_used"]
    assert 0 < len(context.chunks) <= SimpleContextCompressor().max_chunks
    assert all(len(c["text"]) <= SimpleContextCompressor().max_chars_per_chunk for c in context.chunks)
