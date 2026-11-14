"""Uploaded documents: versioning, re-upload decisions (I6) and deletion (I5)."""
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Document
from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.session import SessionLocal
from app.ingestion.file_hash import compute_file_hash
from app.ingestion.upload_storage import UnsafeUploadPath, ensure_inside_root, is_inside_user_dir

logger = logging.getLogger("rag_assistant.documents")

# new        — a file name this user never uploaded: index it.
# changed    — a new version of an existing file name: index it; the old version's chunks are gone.
# unchanged  — an identical re-upload that is already indexed: nothing to index, no doc_version bump.
# reindexed  — an identical re-upload whose row has no chunks (indexing failed, or the row predates
#              document_chunks, v0.2.2): index it again.
UploadStatus = Literal["new", "changed", "unchanged", "reindexed"]


@dataclass(frozen=True)
class RegisteredUpload:
    document: Document
    status: UploadStatus

    @property
    def needs_indexing(self) -> bool:
        return self.status != "unchanged"


def register_document(
    user_id: int,
    file_path: str,
    file_name: str,
    session_factory: sessionmaker = SessionLocal,
    file_size: Optional[int] = None,
) -> RegisteredUpload:
    """The existing row for an identical re-upload, else a new version of ``file_name``.

    ``file_name`` is the client's display name, passed explicitly because stored paths are
    server-generated (G7) and say nothing about what the user called the file.
    """
    with session_factory() as db:
        file_hash = compute_file_hash(file_path)
        existing = documents_repo.latest_version(db, user_id, file_name)

        if existing and existing.file_hash == file_hash:
            indexed = chunks_repo.count_by_document(db, user_id).get(existing.id, 0) > 0
            return RegisteredUpload(existing, "unchanged" if indexed else "reindexed")

        new_version = 1
        if existing:
            existing.is_active = False
            new_version = existing.version + 1
            # I6: an old version's chunks would otherwise stay in the table forever. Search already
            # skips inactive versions; this removes them in the same transaction as the switch.
            chunks_repo.delete_for_documents(
                db, user_id, [d.id for d in documents_repo.list_versions(db, user_id, file_name)]
            )

        doc = Document(
            user_id=user_id,
            file_name=file_name,
            file_path=file_path,
            file_hash=file_hash,
            file_size=file_size,
            version=new_version,
            is_active=True,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return RegisteredUpload(doc, "changed" if existing else "new")


def register_upload(
    user_id: int,
    stored_path: str,
    file_name: str,
    upload_root: Path,
    session_factory: sessionmaker = SessionLocal,
    file_size: Optional[int] = None,
) -> RegisteredUpload:
    """Register a freshly stored upload; the returned row always points at a file this user owns.

    On an identical re-upload the existing row wins. If that row still points at a file in the
    user's own directory, the new copy is redundant and removed. Otherwise the row is moved to
    the new per-user copy:
    - a legacy flat path (pre-G7) may since have been overwritten by another user's upload of
      the same name; that file is left alone, since another user's row may still reference it.
    - the row's file may be gone: rows live in Postgres since Day 14, but Render's disk is
      ephemeral, so a restart deletes the file and keeps the row. Keeping the row's path would
      make the upload index a missing file, every time.
    """
    registered = register_document(user_id, stored_path, file_name, session_factory, file_size)
    doc = registered.document
    if doc.file_path == stored_path:
        return registered

    existing_path = Path(doc.file_path)
    if is_inside_user_dir(upload_root, user_id, existing_path) and existing_path.is_file():
        os.remove(stored_path)
        return registered

    with session_factory() as db:
        row = db.get(Document, doc.id)
        row.file_path = stored_path
        if file_size is not None:
            row.file_size = file_size
        db.commit()
        db.refresh(row)
        return RegisteredUpload(row, registered.status)


@dataclass(frozen=True)
class DeletedDocument:
    versions: int
    chunks: int
    files_removed: int


def delete_document(db: Session, user_id: int, document_id: int, upload_root: Path) -> Optional[DeletedDocument]:
    """Delete a document with every version of its file name (I5): rows, chunks and files.

    None if the user owns no such document. The rows go first and are committed (the database is
    the source of truth; ON DELETE CASCADE takes the chunks); files are removed afterwards, and a
    failure there is logged, never surfaced: the document is already gone for the user. The
    caller bumps doc_version.
    """
    doc = documents_repo.get_owned(db, document_id, user_id)
    if doc is None:
        return None
    versions = documents_repo.list_versions(db, user_id, doc.file_name)
    chunk_counts = chunks_repo.count_by_document(db, user_id)
    chunks = sum(chunk_counts.get(v.id, 0) for v in versions)
    paths = [v.file_path for v in versions]
    for version in versions:
        db.delete(version)
    db.commit()

    return DeletedDocument(versions=len(versions), chunks=chunks, files_removed=_remove_files(upload_root, user_id, paths))


def _remove_files(upload_root: Path, user_id: int, paths: List[str]) -> int:
    """Remove the user's own stored copies. Pre-G7 flat paths may be shared with another user's
    row (G7), so only files inside the user's own directory are deleted."""
    removed = 0
    for raw in paths:
        try:
            path = ensure_inside_root(upload_root, Path(raw))
        except UnsafeUploadPath:
            logger.warning("Not deleting %s of user %s: outside the upload root", raw, user_id)
            continue
        if not is_inside_user_dir(upload_root, user_id, path):
            continue
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Could not delete uploaded file %s", path, exc_info=True)
    return removed
