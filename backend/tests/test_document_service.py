"""G7: an identical re-upload must end up pointing at a file the uploading user owns.

Runs on the suite's own database (SessionLocal: the temp SQLite file, or the Postgres _test
database in CI since Day 14). It is shared with the rest of the suite, so the two users get
database-assigned ids and unique emails.
"""
import uuid
from pathlib import Path
from typing import Tuple

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import Document, User
from app.services.document_service import register_upload
from app.ingestion.upload_storage import new_upload_path
from app.ingestion.file_hash import compute_file_hash

PDF_BYTES = b"%PDF-1.4 the same study notes"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return Path("uploads")


@pytest.fixture
def session_factory() -> sessionmaker:
    from app.db.session import SessionLocal

    return SessionLocal


@pytest.fixture
def users(session_factory: sessionmaker) -> Tuple[int, int]:
    with session_factory() as db:
        first, second = (User(email=f"docs-{uuid.uuid4().hex[:12]}@example.com") for _ in range(2))
        db.add_all([first, second])
        db.commit()
        return first.id, second.id


def _store(root: Path, user_id: int, content: bytes) -> str:
    path = new_upload_path(root, user_id, ".pdf")
    path.write_bytes(content)
    return str(path)


def _add_row(factory: sessionmaker, user_id: int, file_path: str, file_hash: str) -> int:
    with factory() as db:
        doc = Document(
            user_id=user_id, file_name="notes.pdf", file_path=file_path,
            file_hash=file_hash, version=1, is_active=True,
        )
        db.add(doc)
        db.commit()
        return doc.id


def test_reupload_into_own_directory_drops_the_new_copy(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, _ = users
    first = _store(root, owner, PDF_BYTES)
    doc_id = _add_row(session_factory, owner, first, compute_file_hash(first))
    second = _store(root, owner, PDF_BYTES)

    doc = register_upload(owner, second, "notes.pdf", root, session_factory)

    assert doc.id == doc_id
    assert doc.file_path == first
    assert Path(first).exists()
    assert not Path(second).exists()


def test_reupload_after_the_stored_file_vanished_moves_row_to_the_new_copy(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    # Render (no disk) loses uploads on every restart, while the row survives in Postgres. The
    # identical re-upload must restore the document, not delete the only copy left.
    owner, _ = users
    first = _store(root, owner, PDF_BYTES)
    doc_id = _add_row(session_factory, owner, first, compute_file_hash(first))
    Path(first).unlink()

    second = _store(root, owner, PDF_BYTES)
    doc = register_upload(owner, second, "notes.pdf", root, session_factory)

    assert doc.id == doc_id
    assert doc.file_path == second
    assert Path(second).read_bytes() == PDF_BYTES
    with session_factory() as db:
        assert db.get(Document, doc_id).file_path == second


def test_reupload_over_legacy_flat_path_moves_row_to_the_new_copy(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    # The owner registered uploads/notes.pdf before G7; another user then overwrote that shared file.
    owner, _ = users
    legacy = root / "notes.pdf"
    root.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(PDF_BYTES)
    original_hash = compute_file_hash(str(legacy))
    doc_id = _add_row(session_factory, owner, str(legacy), original_hash)
    legacy.write_bytes(b"%PDF-1.4 user two's different notes")

    stored = _store(root, owner, PDF_BYTES)
    doc = register_upload(owner, stored, "notes.pdf", root, session_factory)

    assert doc.id == doc_id
    assert doc.file_path == stored
    assert Path(stored).read_bytes() == PDF_BYTES
    assert legacy.read_bytes() == b"%PDF-1.4 user two's different notes"
    with session_factory() as db:
        assert db.get(Document, doc_id).file_path == stored


def test_new_file_creates_a_row_pointing_at_the_stored_copy(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    _, other = users
    stored = _store(root, other, PDF_BYTES)

    doc = register_upload(other, stored, "notes.pdf", root, session_factory)

    assert doc.file_path == stored
    assert doc.version == 1
