"""document_chunks: write a document's chunks, delete them, and search a user's chunks (Day 15).

The user filter is part of every search query (I1), so a user is never handed fewer than top_k
results because other users' chunks filled an over-fetched window.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import numpy as np
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import bindparam, delete, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.db.models import Chunk
from app.db.models.document_chunk import EMBEDDING_DIMENSIONS, TEXT_SEARCH_CONFIG


@dataclass(frozen=True)
class NewChunk:
    document_id: int
    document_version: int
    page: int | None
    chunk_index: int
    text: str
    content_hash: str
    embedding: np.ndarray
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class ChunkHit:
    id: int
    document_id: int
    file_name: str
    page: int | None
    chunk_index: int
    text: str
    metadata: Dict[str, Any]
    # Vector search: cosine similarity (1 − cosine distance). Keyword search: ts_rank_cd.
    score: float


def insert_many(db: Session, user_id: int, chunks: Sequence[NewChunk]) -> int:
    db.add_all(
        Chunk(
            user_id=user_id,
            document_id=c.document_id,
            document_version=c.document_version,
            page=c.page,
            chunk_index=c.chunk_index,
            text=c.text,
            content_hash=c.content_hash,
            embedding=c.embedding,
            chunk_metadata=c.metadata,
        )
        for c in chunks
    )
    db.flush()
    return len(chunks)


def delete_for_documents(db: Session, user_id: int, document_ids: Sequence[int]) -> int:
    if not document_ids:
        return 0
    result = db.execute(
        delete(Chunk).where(Chunk.user_id == user_id, Chunk.document_id.in_(document_ids))
    )
    return result.rowcount


def embeddings_by_hash(db: Session, user_id: int, content_hashes: Sequence[str]) -> Dict[str, np.ndarray]:
    """{content_hash: stored embedding} for those of the user's chunks whose hash is asked for; one query.

    Only this user's rows (CO3, Day 16, Decision 2A): reuse never crosses users. Inactive versions
    count too, so a changed re-upload reuses the previous version's vectors. The HALFVEC type returns
    a list of the stored float16 values; as float32 they store back as the same halfvec.
    """
    if not content_hashes:
        return {}
    rows = db.execute(
        select(Chunk.content_hash, Chunk.embedding)
        .where(Chunk.user_id == user_id, Chunk.content_hash.in_(set(content_hashes)))
        .distinct(Chunk.content_hash)
    )
    return {content_hash: np.asarray(embedding, dtype=np.float32) for content_hash, embedding in rows}


def count_for_user(db: Session, user_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Chunk).where(Chunk.user_id == user_id)) or 0


def count_by_document(db: Session, user_id: int) -> Dict[int, int]:
    """{document_id: chunk count} for every document of the user that has chunks; one query."""
    rows = db.execute(
        select(Chunk.document_id, func.count())
        .where(Chunk.user_id == user_id)
        .group_by(Chunk.document_id)
    )
    return {document_id: count for document_id, count in rows}


# Raw SQL for the two searches: the operators (<=>, @@) and the OR-ed tsquery read more plainly
# than their SQLAlchemy spellings. Both join documents for the citation name and skip inactive
# versions, so an old version's chunks can never be cited even if a delete was missed.
#
# Two levels (Day 16): identical chunk text (a repeated slide) gives identical vectors, and the sort
# behind ORDER BY distance isn't stable, so exact ties came back in either order from run to run.
# A second sort key in the inner query would stop pgvector's HNSW index from serving it (the index
# serves only ORDER BY <distance> LIMIT k), so the inner query keeps that shape and the outer one
# orders its k rows by (distance, id). A tie straddling the k-th place is still picked by the scan.
_VECTOR_SEARCH = text(
    """
    SELECT top.id, top.document_id, top.file_name, top.page, top.chunk_index, top.text, top.metadata,
           1 - top.distance AS score
    FROM (
        SELECT c.id, c.document_id, d.file_name, c.page, c.chunk_index, c.text, c.metadata,
               c.embedding <=> :query_embedding AS distance
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.user_id = :user_id AND d.is_active AND c.metadata @> :metadata_filter
        ORDER BY c.embedding <=> :query_embedding
        LIMIT :top_k
    ) AS top
    ORDER BY top.distance, top.id
    """
).bindparams(
    bindparam("query_embedding", type_=HALFVEC(EMBEDDING_DIMENSIONS)),
    bindparam("metadata_filter", type_=JSONB),
)

# plainto_tsquery ANDs every term ('recurr' & 'network' & ...), so a natural-language question
# almost never matches a whole chunk and the keyword half would go silent. Replacing & with |
# gives OR semantics: any term matches, and ts_rank_cd orders by how many and how close.
_KEYWORD_SEARCH = text(
    f"""
    WITH q AS (
        SELECT replace(plainto_tsquery('{TEXT_SEARCH_CONFIG}', :query)::text, ' & ', ' | ')::tsquery AS query
    )
    SELECT c.id, c.document_id, d.file_name, c.page, c.chunk_index, c.text, c.metadata,
           ts_rank_cd(c.tsv, q.query) AS score
    FROM document_chunks c
    JOIN documents d ON d.id = c.document_id
    CROSS JOIN q
    WHERE c.user_id = :user_id AND d.is_active AND c.tsv @@ q.query
    ORDER BY score DESC, c.id
    LIMIT :top_k
    """
)


def _hits(rows: Any) -> List[ChunkHit]:
    return [
        ChunkHit(
            id=row.id,
            document_id=row.document_id,
            file_name=row.file_name,
            page=row.page,
            chunk_index=row.chunk_index,
            text=row.text,
            metadata=row.metadata,
            score=float(row.score),
        )
        for row in rows
    ]


def vector_search(
    db: Session,
    user_id: int,
    query_embedding: np.ndarray,
    top_k: int,
    metadata_filter: Dict[str, Any] | None = None,
) -> List[ChunkHit]:
    """``metadata_filter`` keeps chunks whose metadata contains it (jsonb @>), e.g. {"doc_type": "pdf"}."""
    params = {
        "query_embedding": query_embedding,
        "user_id": user_id,
        "top_k": top_k,
        "metadata_filter": metadata_filter or {},
    }
    return _hits(db.execute(_VECTOR_SEARCH, params))


def keyword_search(db: Session, user_id: int, query: str, top_k: int) -> List[ChunkHit]:
    if not query.strip():
        return []
    return _hits(db.execute(_KEYWORD_SEARCH, {"query": query, "user_id": user_id, "top_k": top_k}))
