"""G7, I5, I6: re-upload decisions and document deletion.

Runs on the suite's Postgres database, shared with the rest of the suite, so users get
database-assigned ids and unique emails.
"""
import hashlib
import uuid
from pathlib import Path
from typing import Iterator, List, Tuple

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Chunk, Document, User
from app.db.repositories import chunks as chunks_repo
from app.db.repositories.chunks import NewChunk
from app.ingestion.file_hash import compute_file_hash
from app.ingestion.upload_storage import new_upload_path
from app.retrieval.embeddings import EMBEDDING_DIM
from app.services.document_service import delete_document, register_upload

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
def users(session_factory: sessionmaker) -> Iterator[Tuple[int, int]]:
    with session_factory() as db:
        first, second = (User(email=f"docs-{uuid.uuid4().hex[:12]}@example.com") for _ in range(2))
        db.add_all([first, second])
        db.commit()
        ids = (first.id, second.id)
    yield ids
    with session_factory() as db:
        db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()


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


def _add_chunks(factory: sessionmaker, user_id: int, document_id: int, count: int = 2) -> None:
    vector = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    vector[0] = 1.0
    with factory() as db:
        chunks_repo.insert_many(db, user_id, [
            NewChunk(document_id=document_id, document_version=1, page=1, chunk_index=i, text=f"chunk {i}",
                     content_hash=hashlib.sha256(f"chunk {i}".encode()).hexdigest(), embedding=vector, metadata={})
            for i in range(count)
        ])
        db.commit()


def _chunk_count(factory: sessionmaker, document_ids: List[int]) -> int:
    with factory() as db:
        return db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id.in_(document_ids)))


# --- G7: where the row points -------------------------------------------------------------------

def test_reupload_into_own_directory_drops_the_new_copy(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, _ = users
    first = _store(root, owner, PDF_BYTES)
    doc_id = _add_row(session_factory, owner, first, compute_file_hash(first))
    second = _store(root, owner, PDF_BYTES)

    doc = register_upload(owner, second, "notes.pdf", root, session_factory).document

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
    doc = register_upload(owner, second, "notes.pdf", root, session_factory, file_size=len(PDF_BYTES)).document

    assert doc.id == doc_id
    assert doc.file_path == second
    assert doc.file_size == len(PDF_BYTES)
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
    doc = register_upload(owner, stored, "notes.pdf", root, session_factory).document

    assert doc.id == doc_id
    assert doc.file_path == stored
    assert Path(stored).read_bytes() == PDF_BYTES
    assert legacy.read_bytes() == b"%PDF-1.4 user two's different notes"
    with session_factory() as db:
        assert db.get(Document, doc_id).file_path == stored


# --- I6: new / changed / unchanged / reindexed --------------------------------------------------

def test_a_new_file_is_new_version_1_with_its_size(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    _, other = users
    stored = _store(root, other, PDF_BYTES)

    registered = register_upload(other, stored, "notes.pdf", root, session_factory, file_size=len(PDF_BYTES))

    assert registered.status == "new" and registered.needs_indexing
    assert registered.document.file_path == stored
    assert (registered.document.version, registered.document.file_size) == (1, len(PDF_BYTES))


def test_an_identical_reupload_that_is_indexed_is_unchanged(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, _ = users
    first = register_upload(owner, _store(root, owner, PDF_BYTES), "notes.pdf", root, session_factory).document
    _add_chunks(session_factory, owner, first.id)

    again = register_upload(owner, _store(root, owner, PDF_BYTES), "notes.pdf", root, session_factory)

    assert again.status == "unchanged" and not again.needs_indexing
    assert again.document.id == first.id
    assert _chunk_count(session_factory, [first.id]) == 2


def test_an_identical_reupload_without_chunks_is_reindexed(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    # v0.2.2 rows predate document_chunks, and a failed indexing leaves a row with none: "unchanged"
    # would make those files impossible to index.
    owner, _ = users
    first = register_upload(owner, _store(root, owner, PDF_BYTES), "notes.pdf", root, session_factory).document

    again = register_upload(owner, _store(root, owner, PDF_BYTES), "notes.pdf", root, session_factory)

    assert again.status == "reindexed" and again.needs_indexing
    assert again.document.id == first.id


def test_a_changed_file_is_a_new_version_and_the_old_versions_chunks_are_deleted(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, _ = users
    v1 = register_upload(owner, _store(root, owner, PDF_BYTES), "notes.pdf", root, session_factory).document
    _add_chunks(session_factory, owner, v1.id)

    v2 = register_upload(owner, _store(root, owner, b"%PDF-1.4 revised notes"), "notes.pdf", root, session_factory)

    assert v2.status == "changed" and v2.needs_indexing
    assert v2.document.version == 2
    assert _chunk_count(session_factory, [v1.id]) == 0
    with session_factory() as db:
        assert db.get(Document, v1.id).is_active is False


# --- I5: delete -----------------------------------------------------------------------------------

def test_deleting_a_document_removes_every_version_its_chunks_and_files(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, other = users
    v1_path = _store(root, owner, PDF_BYTES)
    v1 = register_upload(owner, v1_path, "notes.pdf", root, session_factory).document
    v2_path = _store(root, owner, b"%PDF-1.4 revised notes")
    v2 = register_upload(owner, v2_path, "notes.pdf", root, session_factory).document
    _add_chunks(session_factory, owner, v2.id, count=3)
    others = register_upload(other, _store(root, other, PDF_BYTES), "notes.pdf", root, session_factory).document

    with session_factory() as db:
        deleted = delete_document(db, owner, v2.id, root)

    assert deleted is not None
    assert (deleted.versions, deleted.chunks, deleted.files_removed) == (2, 3, 2)
    assert not Path(v1_path).exists() and not Path(v2_path).exists()
    assert _chunk_count(session_factory, [v1.id, v2.id]) == 0
    with session_factory() as db:
        assert db.get(Document, v1.id) is None and db.get(Document, v2.id) is None
        assert db.get(Document, others.id) is not None  # the other user's same-named file stays


def test_deleting_someone_elses_document_is_refused(
    root: Path, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, intruder = users
    doc = register_upload(owner, _store(root, owner, PDF_BYTES), "notes.pdf", root, session_factory).document

    with session_factory() as db:
        assert delete_document(db, intruder, doc.id, root) is None
        assert db.get(Document, doc.id) is not None
