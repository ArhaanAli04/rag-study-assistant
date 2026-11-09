"""B8: FAISS returns squared L2 distances (lower = closer); hybrid fusion must rank the nearest
chunk first, not last."""
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pytest

from app.retrieval.retrieval_service import RetrievalService
from app.retrieval.vector_store import FaissVectorStore
from app.ingestion.models import DocumentChunk
from app.services.caches.query_cache import QueryCache
from app.services.caches.web_cache import WebCache
from tests.fakes import FakeRedis

QUERY = "recurrent networks vanishing gradients"


def _unit(vector: List[float]) -> np.ndarray:
    v = np.array(vector, dtype=np.float32)
    return v / np.linalg.norm(v)


class RealFaissIndexBuilder:
    """A real FaissVectorStore with three chunks at known angles from the query."""

    def __init__(self) -> None:
        self.store = FaissVectorStore(embedding_dim=2)
        self.query_vector = _unit([1.0, 0.0])
        chunks = [
            DocumentChunk(id=name, text=f"{name} {QUERY}", file_name="notes.pdf", page_num=page, chunk_index=0,
                          doc_type="pdf", subject_tags=None, extra_metadata={"document_id": 1})
            for page, name in enumerate(["far", "near", "middle"], start=1)
        ]
        vectors = np.stack([_unit([-1.0, 0.2]), _unit([1.0, 0.05]), _unit([0.5, 0.5])])
        self.store.add_embeddings(vectors, chunks, user_id="1")

    def search(self, query: str, top_k: int = 5, filters: Optional[dict] = None) -> List[Tuple[float, Dict[str, Any]]]:
        return self.store.search(self.query_vector, top_k=top_k, filters=filters)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [[0.0] for _ in texts]


def _service(**weights: float) -> RetrievalService:
    redis_stub = FakeRedis()
    return RetrievalService(
        RealFaissIndexBuilder(), None, QueryCache(redis_stub), WebCache(redis_stub),  # type: ignore[arg-type]
        web_search_enabled=False, l1_cache_enabled=False, **weights,
    )


def test_faiss_returns_distances_nearest_first() -> None:
    results = RealFaissIndexBuilder().search(QUERY, top_k=3, filters={"user_id": "1"})

    assert [meta["id"] for _, meta in results] == ["near", "middle", "far"]
    assert results[0][0] < results[1][0] < results[2][0]


def test_nearest_chunk_ranks_first_after_fusion() -> None:
    result = _service(vector_weight=1.0, keyword_weight=0.0).hybrid_retrieve(QUERY, "1", 0, top_k=3, rerank_top_k=3)

    assert [r["metadata"]["id"] for r in result["results"]] == ["near", "middle", "far"]
    assert result["results"][0]["score"] == pytest.approx(1.0)  # min-max: the nearest normalizes to 1


def test_distance_converts_to_cosine_similarity() -> None:
    store = RealFaissIndexBuilder()
    (distance, meta), = store.search(QUERY, top_k=1, filters={"user_id": "1"})
    cosine = float(np.dot(store.query_vector, _unit([1.0, 0.05])))

    assert meta["id"] == "near"
    assert 1.0 - distance / 2.0 == pytest.approx(cosine, abs=1e-6)
