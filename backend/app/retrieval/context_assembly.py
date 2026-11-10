"""Turn a question into the context the model sees: decompose → hybrid retrieve per sub-query →
parent-page expansion → compression.

The chat (services/chat_pipeline.py) and the retrieval eval (eval/retrieval/) both call this, so
the eval measures exactly what the chat sends to the model.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.retrieval.context_compressor import SimpleContextCompressor
from app.retrieval.query_decomposer import QueryDecomposer
from app.retrieval.retrieval_service import RetrievalService

RERANK_TOP_K = 5
MAX_PARENT_BLOCKS = 3


@dataclass
class AssembledContext:
    chunks: List[Dict[str, Any]]
    confidence: float
    fallback_used: bool
    sub_queries: List[str] = field(default_factory=list)


def assemble_context(
    retrieval_service: RetrievalService,
    query_decomposer: QueryDecomposer,
    compressor: SimpleContextCompressor,
    query: str,
    user_id: str,
    doc_version: int,
    top_k: int,
) -> AssembledContext:
    all_context_chunks: List[Dict[str, Any]] = []
    confidence = 0.0
    fallback_used = False
    sub_queries = query_decomposer.decompose(query)

    for subq in sub_queries:
        retrieval_result = retrieval_service.hybrid_retrieve(
            query=subq, user_id=user_id, doc_version=doc_version,
            top_k=top_k, rerank_top_k=RERANK_TOP_K,
        )
        child_chunks = retrieval_result["results"]
        all_candidates = retrieval_result.get("all_candidates", child_chunks)

        parent_chunks = retrieval_service.expand_to_parent_context(
            top_results=child_chunks,
            all_results=all_candidates,
            max_parents=MAX_PARENT_BLOCKS,
        )
        all_context_chunks.extend(child_chunks + parent_chunks)
        confidence = max(confidence, retrieval_result["confidence"])
        fallback_used = fallback_used or retrieval_result["fallback_used"]

    return AssembledContext(
        chunks=compressor.compress(all_context_chunks),
        confidence=confidence,
        fallback_used=fallback_used,
        sub_queries=list(sub_queries),
    )
