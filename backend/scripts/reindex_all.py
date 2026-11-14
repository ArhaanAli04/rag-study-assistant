"""Rebuild document_chunks from the stored files (Day 16, Decision 4A). Dry run unless --apply.

    python -m scripts.reindex_all                      # list active documents without chunks
    python -m scripts.reindex_all --apply              # index them
    python -m scripts.reindex_all --all --apply        # re-chunk every active document
    python -m scripts.reindex_all --all --re-embed --apply   # also re-embed (after a model change)
    python -m scripts.reindex_all --user 42 ...        # one user only

Run from backend/ against whatever DATABASE_URL / DATABASE_SCHEMA / STORAGE_BACKEND the shell sets
(Render's free plan has no shell, so production runs from a dev machine). It goes through the same
IndexingService as /upload: embeddings of text the user already has stored are reused (CO3), each
document is its own commit together with its user's doc_version bump (so caches never miss new
chunks, even if the run stops halfway), and a document whose file is missing is reported, not
indexed. v0.2.2's production rows have no files (Render had no disk), so they always show up as
"file missing": only a re-upload can fix them.
"""
import argparse
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional

from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.gemini import build_gemini_client
from app.db.models import User
from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.ingestion.upload_storage import FileStorage, StorageError
from app.retrieval.embeddings import EMBED_TEXTS_PER_MINUTE, EmbeddingError, EmbeddingService
from app.services.document_service import stored_copy_is_usable
from app.services.indexing_service import IndexingService

logger = logging.getLogger("rag_assistant.reindex")


@dataclass
class ReindexRow:
    document_id: int
    user_id: int
    file_name: str
    version: int
    chunks_before: int
    action: str  # "would index", "indexed", "skipped: has chunks", "skipped: file missing", "failed: …"
    chunks_after: Optional[int] = None
    embeddings_reused: int = 0
    texts_embedded: int = 0


@dataclass
class ReindexReport:
    applied: bool
    rows: List[ReindexRow] = field(default_factory=list)

    def count(self, action_prefix: str) -> int:
        return sum(1 for r in self.rows if r.action.startswith(action_prefix))

    @property
    def failed(self) -> int:
        return self.count("failed")


def reindex(
    session_factory: sessionmaker,
    storage: FileStorage,
    indexing_service: IndexingService,
    *,
    user_id: Optional[int] = None,
    all_documents: bool = False,
    re_embed: bool = False,
    apply: bool = False,
) -> ReindexReport:
    report = ReindexReport(applied=apply)
    with session_factory() as db:
        documents = [
            (d.id, d.user_id, d.file_name, d.version, d.file_path)
            for d in documents_repo.list_active_for_reindex(db, user_id)
        ]
        chunk_counts = {}
        for owner in {owner for _, owner, _, _, _ in documents}:
            chunk_counts.update(chunks_repo.count_by_document(db, owner))

    for document_id, owner, file_name, version, key in documents:
        row = ReindexRow(document_id, owner, file_name, version, chunk_counts.get(document_id, 0), action="")
        report.rows.append(row)
        if row.chunks_before > 0 and not all_documents:
            row.action = "skipped: has chunks"
        elif not stored_copy_is_usable(storage, owner, key):
            row.action = "skipped: file missing"
        elif not apply:
            row.action = "would index"
        else:
            _index_one(session_factory, storage, indexing_service, row, key, re_embed)
    return report


def _index_one(
    session_factory: sessionmaker,
    storage: FileStorage,
    indexing_service: IndexingService,
    row: ReindexRow,
    key: str,
    re_embed: bool,
) -> None:
    with session_factory() as db:
        superseded = [
            d.id for d in documents_repo.list_versions(db, row.user_id, row.file_name) if d.id != row.document_id
        ]
        try:
            with storage.local_copy(key) as local_path:
                result = indexing_service.index_document(
                    db, file_path=str(local_path), user_id=row.user_id, document_id=row.document_id,
                    document_version=row.version, file_name=row.file_name,
                    superseded_document_ids=superseded, reuse_embeddings=not re_embed,
                )
            # Same commit as the chunks, as on /upload: caches keyed on doc_version see both or neither.
            owner = db.get(User, row.user_id)
            owner.doc_version += 1
            db.commit()
        except (EmbeddingError, StorageError) as error:
            db.rollback()
            row.action = f"failed: {type(error).__name__}"
            logger.warning("Document %s of user %s: %s", row.document_id, row.user_id, error)
            return
    row.action = "indexed"
    row.chunks_after = result.chunks_indexed
    row.embeddings_reused = result.embeddings_reused
    row.texts_embedded = result.texts_embedded


class _CountingModels:
    """Counts embedding requests, so a run can show the API calls it made (0 when all is reused)."""

    def __init__(self, models: Any) -> None:
        self._models = models
        self.requests = 0

    def embed_content(self, **kwargs: Any) -> Any:
        self.requests += 1
        return self._models.embed_content(**kwargs)


class _CountingClient:
    def __init__(self, client: Any) -> None:
        # Hold the client itself, not just its .models: an unreferenced genai.Client is garbage-
        # collected and closes its HTTP client, and every later call fails ("client has been closed").
        self._client = client
        self.models = _CountingModels(client.models)


def _log_report(report: ReindexReport, embedding_requests: int) -> None:
    header = f"{'doc':>6} {'user':>6} {'v':>3} {'chunks':>7}  {'action':<24} {'after':>6} {'reused':>7} {'embedded':>9}  file"
    lines = [header]
    for r in report.rows:
        after = "" if r.chunks_after is None else str(r.chunks_after)
        lines.append(
            f"{r.document_id:>6} {r.user_id:>6} {r.version:>3} {r.chunks_before:>7}  {r.action:<24} "
            f"{after:>6} {r.embeddings_reused:>7} {r.texts_embedded:>9}  {r.file_name}"
        )
    logger.info("\n%s", "\n".join(lines))
    logger.info(
        "%s: %d active documents, %d %s, %d skipped (has chunks), %d skipped (file missing), %d failed; "
        "%d texts embedded in %d embedding requests",
        "Applied" if report.applied else "Dry run (nothing written; add --apply)",
        len(report.rows), report.count("indexed") if report.applied else report.count("would index"),
        "indexed" if report.applied else "would be indexed", report.count("skipped: has"),
        report.count("skipped: file"), report.failed,
        sum(r.texts_embedded for r in report.rows), embedding_requests,
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write; without it nothing changes")
    parser.add_argument("--all", dest="all_documents", action="store_true",
                        help="every active document, not only those without chunks")
    parser.add_argument("--re-embed", action="store_true", help="don't reuse stored embeddings")
    parser.add_argument("--user", type=int, default=None, help="only this user id")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Imported here, not at the top: building them reads Settings and the storage credentials,
    # which the tests (calling reindex() directly) don't need.
    from app.db.session import SessionLocal
    from app.services.container import build_file_storage

    target = make_url(settings.DATABASE_URL.get_secret_value())
    # Names only, never the URL: it carries the password.
    logger.info("Database %s, schema %s, storage %s", target.database, settings.DATABASE_SCHEMA, settings.STORAGE_BACKEND)
    counting = _CountingClient(build_gemini_client())
    # Paced like /upload (per document); between documents the 429 safety net (≥ 60 s) covers the rest.
    indexing = IndexingService(EmbeddingService(counting, texts_per_minute=EMBED_TEXTS_PER_MINUTE))  # type: ignore[arg-type]
    report = reindex(
        SessionLocal, build_file_storage(), indexing,
        user_id=args.user, all_documents=args.all_documents, re_embed=args.re_embed, apply=args.apply,
    )
    _log_report(report, counting.models.requests)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
