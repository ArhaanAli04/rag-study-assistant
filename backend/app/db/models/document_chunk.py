"""One searchable chunk of an uploaded document: its text, embedding and full-text vector (Day 15).

Search runs in Postgres (I4): vectors survive restarts, the user filter is part of the query (I1),
and nothing is rebuilt on add (I2). Deleting a document deletes its chunks (ON DELETE CASCADE, I5).
"""
import datetime

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from app.db.base import Base

# halfvec, not vector (Decision 1B): HNSW on vector stops at 2000 dimensions, on halfvec at 4000,
# so gemini-embedding-001's full 3072 fit at float16 in the space vector(1536) would take.
# Must equal app.retrieval.embeddings.EMBEDDING_DIM; db/ can't import retrieval/ (layering), so
# test_chunk_store checks the two agree.
EMBEDDING_DIMENSIONS = 3072

# 'english' is named because a generated column needs an immutable expression; the one-argument
# to_tsvector depends on the session's default_text_search_config.
TEXT_SEARCH_CONFIG = "english"


# Named Chunk, not DocumentChunk: that is ingestion's parser output (app.ingestion.models), which
# becomes one of these rows once embedded.
class Chunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    document_version = Column(Integer, nullable=False)
    # Page for PDFs, slide for PPTX, NULL for DOCX (no page numbers).
    page = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    # sha256 of text: Day 16's embedding cache (CO3) looks embeddings up by it.
    content_hash = Column(String(64), nullable=False)
    embedding = Column(HALFVEC(EMBEDDING_DIMENSIONS), nullable=False)
    # Written as Postgres reflects it (with ::regconfig), so `alembic check` compares it without a warning.
    tsv = Column(TSVECTOR, Computed(f"to_tsvector('{TEXT_SEARCH_CONFIG}'::regconfig, text)", persisted=True))
    # Parser output the search results carry back: doc_type, subject_tags, slide_title, style.
    chunk_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        # A zero vector has no direction: cosine distance to it is NaN, and before B8 one ranked first.
        # EmbeddingService used to store zeros on an API error; the database now refuses them.
        CheckConstraint("l2_norm(embedding) > 0", name="embedding_not_zero"),
        CheckConstraint("length(btrim(text)) > 0", name="text_not_blank"),
        Index("ix_document_chunks_user_id_document_id", "user_id", "document_id"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "halfvec_cosine_ops"},
        ),
        Index("ix_document_chunks_tsv", "tsv", postgresql_using="gin"),
    )
