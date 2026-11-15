"""B2: retrieval confidence lives on one 0–100 scale, and the forced-web cap is on that scale."""
from typing import Any, Dict

import pytest

from app.retrieval import confidence as conf
from app.retrieval.retrieval_service import RetrievalService
from app.services.caches.query_cache import QueryCache
from app.services.caches.web_cache import WebCache
from tests.fakes import FakeChunkSearch, FakeEmbedder, FakeRedis

QUERY = "explain photosynthesis chlorophyll"
ON_TOPIC = "Photosynthesis uses chlorophyll to turn light into chemical energy."
OFF_TOPIC = "The French Revolution began in 1789."


def equal_chunks(text: str) -> FakeChunkSearch:
    """Five equally scored chunks: normalized they all score 1.0, so the raw confidence is 80."""
    return FakeChunkSearch(vector=[
        {"score": 0.9, "text": text, "metadata": {"file_name": "notes.pdf", "chunk_index": i}}
        for i in range(5)
    ])


def _service(text: str) -> RetrievalService:
    redis_stub = FakeRedis()
    return RetrievalService(
        FakeEmbedder(), equal_chunks(text), QueryCache(redis_stub), WebCache(redis_stub)  # type: ignore[arg-type]
    )


def _retrieve(text: str) -> Dict[str, Any]:
    service = _service(text)
    # TAVILY_API_KEY is empty in tests, so web search raises and retrieval continues without it.
    return service.hybrid_retrieve(QUERY, user_id="1", doc_version=0, top_k=5)


def test_matching_chunks_keep_their_full_confidence() -> None:
    result = _retrieve(ON_TOPIC)

    assert result["confidence"] == pytest.approx(80.0)
    assert result["fallback_used"] is False


def test_forced_web_caps_at_30_on_the_0_to_100_scale() -> None:
    # No query keyword in any chunk → confidence halved to 40, then capped. Before B2 the cap was
    # 0.3, so with web search off the answer was always grounded as "none".
    result = _retrieve(OFF_TOPIC)

    assert result["confidence"] == pytest.approx(conf.FORCED_WEB_CAP) == pytest.approx(30.0)
    assert result["fallback_used"] is True
    assert conf.grounding_level(result["confidence"]) == "loose"


@pytest.mark.parametrize(
    ("score", "level"),
    [(100.0, "strict"), (70.0, "strict"), (69.9, "loose"), (30.0, "loose"), (29.9, "none"), (0.3, "none")],
)
def test_grounding_thresholds(score: float, level: str) -> None:
    assert conf.grounding_level(score) == level


def test_l1_cache_is_per_instance() -> None:
    first, second = _service(ON_TOPIC), _service(ON_TOPIC)
    first.l1_cache_store("1", QUERY, 0, {"results": []})

    assert second.l1_cache_lookup("1", QUERY, 0) is None
