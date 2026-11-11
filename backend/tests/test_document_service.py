"""G7: an identical re-upload must end up pointing at a file the uploading user owns."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
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
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([User(id=1, email="a@example.com"), User(id=2, email="b@example.com")])
        db.commit()
    return factory


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
    root: Path, session_factory: sessionmaker
) -> None:
    first = _store(root, 1, PDF_BYTES)
    doc_id = _add_row(session_factory, 1, first, compute_file_hash(first))
    second = _store(root, 1, PDF_BYTES)

    doc = register_upload(1, second, "notes.pdf", root, session_factory)

    assert doc.id == doc_id
    assert doc.file_path == first
    assert Path(first).exists()
    assert not Path(second).exists()


def test_reupload_over_legacy_flat_path_moves_row_to_the_new_copy(
    root: Path, session_factory: sessionmaker
) -> None:
    # User 1 registered uploads/notes.pdf before G7; user 2 then overwrote that shared file.
    legacy = root / "notes.pdf"
    root.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(PDF_BYTES)
    original_hash = compute_file_hash(str(legacy))
    doc_id = _add_row(session_factory, 1, str(legacy), original_hash)
    legacy.write_bytes(b"%PDF-1.4 user two's different notes")

    stored = _store(root, 1, PDF_BYTES)
    doc = register_upload(1, stored, "notes.pdf", root, session_factory)

    assert doc.id == doc_id
    assert doc.file_path == stored
    assert Path(stored).read_bytes() == PDF_BYTES
    assert legacy.read_bytes() == b"%PDF-1.4 user two's different notes"
    with session_factory() as db:
        assert db.get(Document, doc_id).file_path == stored


def test_new_file_creates_a_row_pointing_at_the_stored_copy(
    root: Path, session_factory: sessionmaker
) -> None:
    stored = _store(root, 2, PDF_BYTES)

    doc = register_upload(2, stored, "notes.pdf", root, session_factory)

    assert doc.file_path == stored
    assert doc.version == 1
