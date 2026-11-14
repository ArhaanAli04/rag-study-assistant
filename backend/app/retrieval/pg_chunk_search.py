"""Hybrid retrieval's two candidate lists, from Postgres (Day 15: replaces FAISS + BM25).

Both queries run in one session, so one retrieval costs one connection checkout and one
transaction instead of two (CO6: every round trip crosses Render Singapore → Supabase Mumbai).
Results keep the metadata shape the FAISS / BM25 indexes produced, so fusion, parent-page
expansion, citations and the eval read them unchanged.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

import numpy as np
from sqlalchemy.orm import sessionmaker

from app.db.repositories import chunks as chunks_repo
from app.db.repositories.chunks import ChunkHit

# Keys of document_chunks.metadata that are top-level fields of a search result; the rest of the
# parser's metadata (slide_title, style, …) goes back into extra_metadata, where it came from.
TOP_LEVEL_METADATA = ("doc_type", "subject_tags")


@dataclass
class Candidates:
    vector: List[Dict[str, Any]] = field(default_factory=list)
    keyword: List[Dict[str, Any]] = field(default_factory=list)


def result_dict(hit: ChunkHit, user_id: int) -> Dict[str, Any]:
    """One search result: {"score", "text", "metadata"}, metadata as the old indexes stored it."""
    stored = hit.metadata or {}
    extra = {k: v for k, v in stored.items() if k not in TOP_LEVEL_METADATA}
    return {
        "score": hit.score,
        "text": hit.text,
        "metadata": {
            "id": hit.id,
            "text": hit.text,
            "file_name": hit.file_name,
            "page_num": hit.page,
            "chunk_index": hit.chunk_index,
            "doc_type": stored.get("doc_type"),
            "subject_tags": stored.get("subject_tags"),
            "extra_metadata": {**extra, "document_id": hit.document_id},
            # Retrieval metadata keeps string user ids (CLAUDE.md); the database filter uses the int.
            "user_id": str(user_id),
            "document_id": hit.document_id,
        },
    }


class PgChunkSearch:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def search(self, query_embedding: np.ndarray, keyword_query: str, user_id: str, top_k: int) -> Candidates:
        """Top-k by cosine similarity and top-k by ts_rank_cd, among this user's chunks only."""
        owner = int(user_id)
        with self.session_factory() as db:
            vector = chunks_repo.vector_search(db, owner, query_embedding, top_k)
            keyword = chunks_repo.keyword_search(db, owner, keyword_query, top_k)
        return Candidates(
            vector=[result_dict(h, owner) for h in vector],
            keyword=[result_dict(h, owner) for h in keyword],
        )

    def vector_only(
        self, query_embedding: np.ndarray, user_id: str, top_k: int, metadata_filter: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """POST /search: the vector half alone, with optional metadata filters in the WHERE clause."""
        owner = int(user_id)
        with self.session_factory() as db:
            hits = chunks_repo.vector_search(db, owner, query_embedding, top_k, metadata_filter)
        return [result_dict(h, owner) for h in hits]
