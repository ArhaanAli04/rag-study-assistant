"""Uploaded documents: storing, versioning, re-upload decisions (I6) and deletion (I5)."""
import hashlib
import logging
from dataclasses import dataclass
from typing import Literal, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Document
from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.session import SessionLocal
from app.ingestion.upload_storage import (
    FileStorage,
    StorageError,
    UnsafeUploadPath,
    file_extension,
    is_user_key,
    new_upload_key,
)

logger = logging.getLogger("rag_assistant.documents")

# new        — a file name this user never uploaded: index it.
# changed    — a new version of an existing file name: index it; indexing then replaces the earlier
#              versions' chunks (they stay until then, so unchanged chunks reuse their vectors, CO3).
# unchanged  — an identical re-upload that is already indexed: nothing to index, no doc_version bump.
# reindexed  — an identical re-upload whose row has no chunks (indexing failed, or the row predates
#              document_chunks, v0.2.2): index it again.
UploadStatus = Literal["new", "changed", "unchanged", "reindexed"]


@dataclass(frozen=True)
class RegisteredUpload:
    document: Document
    status: UploadStatus
    # The same file name's earlier versions (inactive), whose chunks indexing deletes in its commit.
    superseded_document_ids: Tuple[int, ...] = ()

    @property
    def needs_indexing(self) -> bool:
        return self.status != "unchanged"


def _stored_copy_is_usable(storage: FileStorage, user_id: int, key: str) -> bool:
    """The row's file is this user's own (not a pre-G7 shared flat path) and still exists.

    Before Day 15 Render's disk was wiped on every restart while the row survived in Postgres;
    an identical re-upload must then restore the file, not trust the row.
    """
    if not is_user_key(user_id, key):
        return False
    try:
        return storage.exists(key)
    except UnsafeUploadPath:
        return False


def register_upload(
    user_id: int,
    content: bytes,
    file_name: str,
    storage: FileStorage,
    session_factory: sessionmaker = SessionLocal,
) -> RegisteredUpload:
    """Store an upload (if needed) and record it; the returned row always points at a stored file
    this user owns.

    ``file_name`` is the client's display name, passed explicitly because stored keys are
    server-generated (G7) and say nothing about what the user called the file. The object is
    written before its row is committed: a crash in between leaves an orphan object (cheap to
    sweep), never a row pointing at nothing.
    """
    file_hash = hashlib.sha256(content).hexdigest()
    with session_factory() as db:
        existing = documents_repo.latest_version(db, user_id, file_name)

        if existing and existing.file_hash == file_hash:
            indexed = chunks_repo.count_by_document(db, user_id).get(existing.id, 0) > 0
            status: UploadStatus = "unchanged" if indexed else "reindexed"
            if not _stored_copy_is_usable(storage, user_id, existing.file_path):
                # The row's file is gone, or it is a legacy flat path that another user's upload may
                # have overwritten (that file is left alone: another row may still use it).
                key = new_upload_key(user_id, file_extension(file_name))
                storage.put(key, content)
                existing.file_path = key
            existing.file_size = len(content)
            # A changed upload whose indexing failed left the earlier versions' chunks behind; its
            # identical re-upload ("reindexed") replaces them too.
            earlier = tuple(
                d.id for d in documents_repo.list_versions(db, user_id, file_name) if d.id != existing.id
            ) if status == "reindexed" else ()
            db.commit()
            db.refresh(existing)
            return RegisteredUpload(existing, status, earlier)

        key = new_upload_key(user_id, file_extension(file_name))
        storage.put(key, content)
        try:
            new_version = 1
            superseded: Tuple[int, ...] = ()
            if existing:
                existing.is_active = False
                new_version = existing.version + 1
                # Search skips inactive versions at once; their chunks are deleted by the indexing
                # commit (after their vectors were offered for reuse), or by the next upload or reindex
                # if indexing fails.
                superseded = tuple(d.id for d in documents_repo.list_versions(db, user_id, file_name))
            doc = Document(
                user_id=user_id,
                file_name=file_name,
                file_path=key,
                file_hash=file_hash,
                file_size=len(content),
                version=new_version,
                is_active=True,
            )
            db.add(doc)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            _delete_quietly(storage, key)
            raise
        db.refresh(doc)
        return RegisteredUpload(doc, "changed" if existing else "new", superseded)


@dataclass(frozen=True)
class DeletedDocument:
    versions: int
    chunks: int
    files_removed: int


def delete_document(db: Session, user_id: int, document_id: int, storage: FileStorage) -> Optional[DeletedDocument]:
    """Delete a document with every version of its file name (I5): rows, chunks and stored files.

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
    keys = [v.file_path for v in versions]
    for version in versions:
        db.delete(version)
    db.commit()

    # Pre-G7 flat keys may be shared with another user's row, so only the user's own are removed.
    removed = sum(1 for key in keys if is_user_key(user_id, key) and _delete_quietly(storage, key))
    return DeletedDocument(versions=len(versions), chunks=chunks, files_removed=removed)


def _delete_quietly(storage: FileStorage, key: str) -> bool:
    try:
        return storage.delete(key)
    except (StorageError, UnsafeUploadPath):
        logger.warning("Could not delete stored file %s", key, exc_info=True)
        return False
