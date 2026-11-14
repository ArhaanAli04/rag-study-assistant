"""G7, I5, I6: re-upload decisions, where a document's file lives, and document deletion.

Runs on the suite's Postgres database, shared with the rest of the suite, so users get
database-assigned ids and unique emails. Files go through the same FileStorage protocol the app
uses: a local directory, and once on the fake S3 bucket.
"""
import hashlib
import uuid
from pathlib import Path
from typing import Any, Iterator, List, Tuple

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Chunk, Document, User
from app.db.repositories import chunks as chunks_repo
from app.db.repositories.chunks import NewChunk
from app.ingestion.upload_storage import LocalFileStorage, S3FileStorage
from app.retrieval.embeddings import EMBEDDING_DIM
from app.services.document_service import delete_document, register_upload
from tests.fakes import FakeS3Client

PDF_BYTES = b"%PDF-1.4 the same study notes"
REVISED = b"%PDF-1.4 revised notes"


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path)


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


def _register(storage: Any, factory: sessionmaker, user_id: int, content: bytes = PDF_BYTES) -> Any:
    return register_upload(user_id, content, "notes.pdf", storage, factory)


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


# --- where the file lives (G7, Day 15) ------------------------------------------------------------

def test_a_new_file_is_stored_under_the_users_prefix_with_its_size(
    storage: LocalFileStorage, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, _ = users

    registered = _register(storage, session_factory, owner)

    doc = registered.document
    assert registered.status == "new" and registered.needs_indexing
    assert doc.file_path.startswith(f"uploads/{owner}/") and doc.file_path.endswith(".pdf")
    assert (doc.version, doc.file_size) == (1, len(PDF_BYTES))
    with storage.local_copy(doc.file_path) as path:
        assert path.read_bytes() == PDF_BYTES


def test_an_identical_reupload_stores_nothing_new(
    storage: LocalFileStorage, session_factory: sessionmaker, users: Tuple[int, int], tmp_path: Path
) -> None:
    owner, _ = users
    first = _register(storage, session_factory, owner).document

    again = _register(storage, session_factory, owner).document

    assert again.id == first.id and again.file_path == first.file_path
    assert len(list((tmp_path / "uploads" / str(owner)).iterdir())) == 1


def test_a_reupload_after_the_stored_file_vanished_restores_it(
    storage: LocalFileStorage, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    # Render's disk lost every upload on restart while the row survived in Postgres. The identical
    # re-upload must store a fresh copy and re-link the row, not trust the row.
    owner, _ = users
    first = _register(storage, session_factory, owner).document
    storage.delete(first.file_path)

    again = _register(storage, session_factory, owner).document

    assert again.id == first.id and again.file_path != first.file_path
    assert storage.exists(again.file_path)


def test_a_reupload_over_a_legacy_flat_key_moves_the_row_and_leaves_the_shared_file(
    storage: LocalFileStorage, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    # Before G7 uploads/notes.pdf was shared by every user who uploaded that name; another user has
    # since overwritten it. The owner's identical re-upload gets its own copy; the shared file stays.
    owner, _ = users
    storage.put("uploads/notes.pdf", b"%PDF-1.4 user two's different notes")
    with session_factory() as db:
        legacy = Document(user_id=owner, file_name="notes.pdf", file_path="uploads/notes.pdf",
                          file_hash=hashlib.sha256(PDF_BYTES).hexdigest(), version=1, is_active=True)
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id

    doc = _register(storage, session_factory, owner).document

    assert doc.id == legacy_id and doc.file_path.startswith(f"uploads/{owner}/")
    with storage.local_copy("uploads/notes.pdf") as path:
        assert path.read_bytes() == b"%PDF-1.4 user two's different notes"


# --- I6: new / changed / unchanged / reindexed ------------------------------------------------------

def test_an_identical_reupload_that_is_indexed_is_unchanged(
    storage: LocalFileStorage, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, _ = users
    first = _register(storage, session_factory, owner).document
    _add_chunks(session_factory, owner, first.id)

    again = _register(storage, session_factory, owner)

    assert again.status == "unchanged" and not again.needs_indexing
    assert _chunk_count(session_factory, [first.id]) == 2


def test_an_identical_reupload_without_chunks_is_reindexed(
    storage: LocalFileStorage, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    # v0.2.2 rows predate document_chunks, and a failed indexing leaves a row with none: "unchanged"
    # would make those files impossible to index.
    owner, _ = users
    first = _register(storage, session_factory, owner).document

    again = _register(storage, session_factory, owner)

    assert again.status == "reindexed" and again.needs_indexing
    assert again.document.id == first.id


def test_a_changed_file_is_a_new_version_and_the_old_versions_chunks_are_deleted(
    storage: LocalFileStorage, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, _ = users
    v1 = _register(storage, session_factory, owner).document
    _add_chunks(session_factory, owner, v1.id)

    v2 = _register(storage, session_factory, owner, REVISED)

    assert v2.status == "changed" and v2.needs_indexing
    assert v2.document.version == 2 and v2.document.file_path != v1.file_path
    assert _chunk_count(session_factory, [v1.id]) == 0
    with session_factory() as db:
        assert db.get(Document, v1.id).is_active is False


# --- I5: delete -----------------------------------------------------------------------------------

def test_deleting_a_document_removes_every_version_its_chunks_and_files(
    storage: LocalFileStorage, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, other = users
    v1 = _register(storage, session_factory, owner).document
    v2 = _register(storage, session_factory, owner, REVISED).document
    _add_chunks(session_factory, owner, v2.id, count=3)
    others = _register(storage, session_factory, other).document

    with session_factory() as db:
        deleted = delete_document(db, owner, v2.id, storage)

    assert deleted is not None
    assert (deleted.versions, deleted.chunks, deleted.files_removed) == (2, 3, 2)
    assert not storage.exists(v1.file_path) and not storage.exists(v2.file_path)
    assert _chunk_count(session_factory, [v1.id, v2.id]) == 0
    with session_factory() as db:
        assert db.get(Document, v1.id) is None and db.get(Document, v2.id) is None
        assert db.get(Document, others.id) is not None  # the other user's same-named file stays
    assert storage.exists(others.file_path)


def test_deleting_someone_elses_document_is_refused(
    storage: LocalFileStorage, session_factory: sessionmaker, users: Tuple[int, int]
) -> None:
    owner, intruder = users
    doc = _register(storage, session_factory, owner).document

    with session_factory() as db:
        assert delete_document(db, intruder, doc.id, storage) is None
        assert db.get(Document, doc.id) is not None
    assert storage.exists(doc.file_path)


# --- the same flow on object storage --------------------------------------------------------------

def test_upload_reupload_and_delete_on_s3(session_factory: sessionmaker, users: Tuple[int, int]) -> None:
    client = FakeS3Client()
    storage = S3FileStorage(client, client.bucket)
    owner, _ = users

    first = _register(storage, session_factory, owner)
    again = _register(storage, session_factory, owner)

    assert first.status == "new" and again.status == "reindexed"  # no chunks were added here
    assert list(client.objects) == [first.document.file_path]
    assert client.objects[first.document.file_path] == PDF_BYTES
    with session_factory() as db:
        assert delete_document(db, owner, first.document.id, storage).files_removed == 1
    assert client.objects == {}
