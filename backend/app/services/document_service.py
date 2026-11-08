#versioning logic
import os
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.db.database import SessionLocal, Document
from app.ingestion.upload_storage import is_inside_user_dir
from app.ingestion.file_hash import compute_file_hash


def register_document(
    user_id: int,
    file_path: str,
    file_name: str,
    session_factory: sessionmaker = SessionLocal,
) -> Document:
    """Return the existing row for an identical re-upload, else a new version of ``file_name``.

    ``file_name`` is the client's display name, passed explicitly because stored paths are
    server-generated (G7) and say nothing about what the user called the file.
    """
    db = session_factory()
    try:
        file_hash = compute_file_hash(file_path)

        existing = (
            db.query(Document)
            .filter(Document.user_id == user_id, Document.file_name == file_name)
            .order_by(Document.version.desc())
            .first()
        )

        if existing and existing.file_hash == file_hash:
            return existing

        new_version = 1
        if existing:
            existing.is_active = False
            db.add(existing)
            new_version = existing.version + 1

        doc = Document(
            user_id=user_id,
            file_name=file_name,
            file_path=file_path,
            file_hash=file_hash,
            version=new_version,
            is_active=True,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc
    finally:
        db.close()


def register_upload(
    user_id: int,
    stored_path: str,
    file_name: str,
    upload_root: Path,
    session_factory: sessionmaker = SessionLocal,
) -> Document:
    """Register a freshly stored upload; the returned row always points at a file this user owns.

    On an identical re-upload the existing row wins. If that row already points into the
    user's own directory, the new copy is redundant and removed. If it points at a legacy
    flat path (pre-G7), that file may since have been overwritten by another user's upload of
    the same name, so the row is moved to the new per-user copy and the legacy file is left
    alone (another user's row may still reference it).
    """
    doc = register_document(user_id, stored_path, file_name, session_factory)
    if doc.file_path == stored_path:
        return doc

    if is_inside_user_dir(upload_root, user_id, Path(doc.file_path)):
        os.remove(stored_path)
        return doc

    db = session_factory()
    try:
        row = db.get(Document, doc.id)
        row.file_path = stored_path
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()
