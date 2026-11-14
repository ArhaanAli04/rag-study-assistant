"""Index one uploaded document: parse → chunk → embed → document_chunks (Day 15).

The use case lives in services/ because it spans layers: ingestion parses and chunks, retrieval
embeds, db stores. Until Day 15 ingestion/indexing_pipeline.py wrote into retrieval's in-memory
indexes itself (a sideways import listed in docs/architecture/layout.md).
"""
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import numpy as np
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
    # CO3 (Day 16): chunks whose vector came from the user's stored chunks of identical text, and the
    # texts actually sent to the API (identical texts within one document are embedded once).
    embeddings_reused: int = 0
    texts_embedded: int = 0


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        superseded_document_ids: Sequence[int] = (),
        reuse_embeddings: bool = True,
    ) -> IndexingResult:
        """Replace the chunks of the document and of its superseded versions. Flushes; the caller commits.

        Vectors of text the user already has stored are reused (CO3); only the rest is embedded.
        ``reuse_embeddings=False`` embeds everything (after a model change, via the reindex script).
        Raises EmbeddingError if any embedding call fails: nothing is written or deleted then, so a
        document is either fully indexed or not at all, and its old chunks stay as they were.
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

        hashes = [content_hash(c.text) for c in kept]
        # Looked up before the delete below, so re-indexing a document reuses its own vectors.
        vectors: Dict[str, np.ndarray] = (
            chunks_repo.embeddings_by_hash(db, user_id, hashes) if reuse_embeddings else {}
        )
        reused = sum(1 for h in hashes if h in vectors)
        to_embed = {h: c.text for h, c in zip(hashes, kept) if h not in vectors}
        if to_embed:
            vectors.update(zip(to_embed, self.embedding_service.embed_texts(list(to_embed.values()))))

        rows = [
            NewChunk(
                document_id=document_id,
                document_version=document_version,
                page=c.page_num,
                chunk_index=c.chunk_index,
                text=c.text,
                content_hash=h,
                embedding=vectors[h],
                metadata=_stored_metadata(c),
            )
            for c, h in zip(kept, hashes)
        ]
        chunks_repo.delete_for_documents(db, user_id, [document_id, *superseded_document_ids])
        chunks_repo.insert_many(db, user_id, rows)
        logger.info(
            "Document %s: %d chunks, %d reused, %d texts embedded, %d blank skipped",
            document_id, len(rows), reused, len(to_embed), skipped,
        )
        return IndexingResult(
            chunks_indexed=len(rows), blank_chunks_skipped=skipped,
            embeddings_reused=reused, texts_embedded=len(to_embed),
        )
