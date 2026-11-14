"""Index one uploaded document: parse → chunk → embed → document_chunks (Day 15).

The use case lives in services/ because it spans layers: ingestion parses and chunks, retrieval
embeds, db stores. Until Day 15 ingestion/indexing_pipeline.py wrote into retrieval's in-memory
indexes itself (a sideways import listed in docs/architecture/layout.md).
"""
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.db.repositories import chunks as chunks_repo
from app.db.repositories.chunks import NewChunk
from app.ingestion.chunk_builder import build_chunks_for_file
from app.ingestion.models import DocumentChunk
from app.retrieval.embeddings import EmbeddingService

logger = logging.getLogger("rag_assistant.indexing")


@dataclass(frozen=True)
class IndexingResult:
    chunks_indexed: int
    # B10: the PPTX chunker emits empty chunks (e.g. image-only slides). The API rejects blank
    # text, and the database refuses it, so they are skipped and counted instead of embedded.
    blank_chunks_skipped: int


def _storable_text(text: str) -> str:
    # Postgres text can't hold NUL characters, which some PDFs' text layers contain.
    return text.replace("\x00", "")


def _stored_metadata(chunk: DocumentChunk) -> Dict[str, Any]:
    """Parser metadata worth keeping; the document id is a column of its own."""
    extra = {k: v for k, v in (chunk.extra_metadata or {}).items() if k != "document_id"}
    return {"doc_type": chunk.doc_type, "subject_tags": chunk.subject_tags, **extra}


class IndexingService:
    def __init__(self, embedding_service: EmbeddingService) -> None:
        self.embedding_service = embedding_service

    def index_document(
        self,
        db: Session,
        *,
        file_path: str,
        user_id: int,
        document_id: int,
        document_version: int,
        file_name: str,
        subject_tags: str | None = None,
    ) -> IndexingResult:
        """Replace the document's chunks with freshly embedded ones. Flushes; the caller commits.

        Raises EmbeddingError if any embedding call fails: nothing is written then, so a document
        is either fully indexed or not at all, never stored with zero vectors.
        """
        parsed = build_chunks_for_file(
            file_path, subject_tags=subject_tags, document_id=document_id, file_name=file_name
        )
        kept: List[DocumentChunk] = []
        for chunk in parsed:
            chunk.text = _storable_text(chunk.text)
            if chunk.text.strip():
                kept.append(chunk)
        skipped = len(parsed) - len(kept)

        embeddings = self.embedding_service.embed_texts([c.text for c in kept])
        rows = [
            NewChunk(
                document_id=document_id,
                document_version=document_version,
                page=c.page_num,
                chunk_index=c.chunk_index,
                text=c.text,
                content_hash=hashlib.sha256(c.text.encode("utf-8")).hexdigest(),
                embedding=embedding,
                metadata=_stored_metadata(c),
            )
            for c, embedding in zip(kept, embeddings)
        ]
        chunks_repo.delete_for_documents(db, user_id, [document_id])
        chunks_repo.insert_many(db, user_id, rows)
        if skipped:
            logger.info("Document %s: skipped %d blank chunks of %d", document_id, skipped, len(parsed))
        return IndexingResult(chunks_indexed=len(rows), blank_chunks_skipped=skipped)
