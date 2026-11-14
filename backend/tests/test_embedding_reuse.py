"""CO3 (Day 16): indexing reuses the user's stored vectors of identical text instead of re-embedding.

Runs on the suite's Postgres database. Parsing is stubbed (the texts are the test's), embedding is the
suite's fake Gemini (counted per call), and uploads go through the real register_upload, so the
changed-version path is the one /upload takes.
"""
import uuid
from pathlib import Path
from typing import Callable, Iterator, List, Tuple

import numpy as np
import pytest
from sqlalchemy import select

from app.db.models import Chunk, User
from app.db.session import SessionLocal
from app.ingestion.models import DocumentChunk
from app.ingestion.upload_storage import LocalFileStorage
from app.retrieval.embeddings import EMBEDDING_DIM, EmbeddingError, EmbeddingService
from app.retrieval.pg_chunk_search import PgChunkSearch
from app.services import indexing_service as indexing_module
from app.services.document_service import RegisteredUpload, register_upload
from app.services.indexing_service import IndexingResult, IndexingService
from tests.fakes import FakeGemini, FakeGenaiClient, fake_embedding

V1 = ["Recurrent networks suffer from vanishing gradients.", "LSTMs add a gated cell state.", "GRUs merge two gates."]
# One slide edited, the rest identical.
V2 = [V1[0], "LSTMs add a gated cell state and a forget gate.", V1[2]]


@pytest.fixture
def users() -> Iterator[Tuple[int, int]]:
    with SessionLocal() as db:
        first, second = (User(email=f"reuse-{uuid.uuid4().hex[:12]}@example.com") for _ in range(2))
        db.add_all([first, second])
        db.commit()
        ids = (first.id, second.id)
    yield ids
    with SessionLocal() as db:
        db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()


@pytest.fixture
def parses_as(monkeypatch: pytest.MonkeyPatch) -> Callable[[List[str]], None]:
    """Make the next indexing parse to these chunk texts, one per page."""

    def set_texts(texts: List[str]) -> None:
        chunks = [
            DocumentChunk(id=str(i), text=t, file_name="notes.pdf", page_num=i, chunk_index=0, doc_type="pdf")
            for i, t in enumerate(texts, start=1)
        ]
        monkeypatch.setattr(indexing_module, "build_chunks_for_file", lambda *args, **kwargs: list(chunks))

    return set_texts


def _service() -> IndexingService:
    return IndexingService(EmbeddingService(FakeGenaiClient()))  # type: ignore[arg-type]


def _upload(storage: LocalFileStorage, user_id: int, content: bytes) -> RegisteredUpload:
    return register_upload(user_id, content, "notes.pdf", storage, SessionLocal)


def _index(registered: RegisteredUpload, reuse: bool = True) -> IndexingResult:
    doc = registered.document
    with SessionLocal() as db:
        result = _service().index_document(
            db, file_path="stubbed", user_id=doc.user_id, document_id=doc.id, document_version=doc.version,
            file_name=doc.file_name, superseded_document_ids=registered.superseded_document_ids,
            reuse_embeddings=reuse,
        )
        db.commit()
    return result


def _chunk_texts(document_id: int) -> List[str]:
    with SessionLocal() as db:
        return list(db.scalars(select(Chunk.text).where(Chunk.document_id == document_id).order_by(Chunk.page)))


def test_reindexing_identical_text_makes_no_embedding_call(
    tmp_path: Path, users: Tuple[int, int], gemini: FakeGemini, parses_as: Callable[[List[str]], None]
) -> None:
    owner, _ = users
    parses_as(V1)
    registered = _upload(LocalFileStorage(tmp_path), owner, b"v1")
    first = _index(registered)
    calls_after_first = gemini.embed_calls

    again = _index(registered)

    assert (first.embeddings_reused, first.texts_embedded) == (0, 3)
    assert (again.embeddings_reused, again.texts_embedded) == (3, 0)
    assert gemini.embed_calls == calls_after_first
    assert _chunk_texts(registered.document.id) == V1


def test_reuse_can_be_turned_off_for_a_model_change(
    tmp_path: Path, users: Tuple[int, int], gemini: FakeGemini, parses_as: Callable[[List[str]], None]
) -> None:
    owner, _ = users
    parses_as(V1)
    registered = _upload(LocalFileStorage(tmp_path), owner, b"v1")
    _index(registered)

    forced = _index(registered, reuse=False)

    assert (forced.embeddings_reused, forced.texts_embedded) == (0, 3)


def test_identical_text_within_a_document_is_embedded_once(
    tmp_path: Path, users: Tuple[int, int], gemini: FakeGemini, parses_as: Callable[[List[str]], None]
) -> None:
    owner, _ = users
    parses_as(["Same footer on every slide.", "Real content.", "Same footer on every slide."])

    result = _index(_upload(LocalFileStorage(tmp_path), owner, b"deck"))

    assert (result.chunks_indexed, result.texts_embedded) == (3, 2)


def test_another_users_identical_text_is_not_reused(
    tmp_path: Path, users: Tuple[int, int], gemini: FakeGemini, parses_as: Callable[[List[str]], None]
) -> None:
    # Decision 2A: reuse never crosses users, so one user's uploads can't reveal what another stored.
    owner, other = users
    storage = LocalFileStorage(tmp_path)
    parses_as(V1)
    _index(_upload(storage, owner, b"shared course notes"))

    theirs = _index(_upload(storage, other, b"shared course notes"))

    assert (theirs.embeddings_reused, theirs.texts_embedded) == (0, 3)


def test_a_changed_upload_embeds_only_the_changed_chunks_and_leaves_no_old_chunks(
    tmp_path: Path, users: Tuple[int, int], gemini: FakeGemini, parses_as: Callable[[List[str]], None]
) -> None:
    owner, _ = users
    storage = LocalFileStorage(tmp_path)
    parses_as(V1)
    v1 = _upload(storage, owner, b"v1")
    _index(v1)
    parses_as(V2)
    v2 = _upload(storage, owner, b"v2")
    assert v2.status == "changed" and v2.superseded_document_ids == (v1.document.id,)
    calls_before = gemini.embed_calls

    result = _index(v2)

    assert (result.embeddings_reused, result.texts_embedded) == (2, 1)
    assert gemini.embed_calls == calls_before + 1  # one batch holding the one changed text
    assert _chunk_texts(v1.document.id) == []
    assert _chunk_texts(v2.document.id) == V2


def test_a_changed_upload_whose_embedding_fails_keeps_the_old_chunks_unsearchable(
    tmp_path: Path, users: Tuple[int, int], gemini: FakeGemini, parses_as: Callable[[List[str]], None]
) -> None:
    owner, _ = users
    storage = LocalFileStorage(tmp_path)
    parses_as(V1)
    v1 = _upload(storage, owner, b"v1")
    _index(v1)
    parses_as(V2)
    v2 = _upload(storage, owner, b"v2")
    gemini.embeddings_down = True

    with pytest.raises(EmbeddingError):
        _index(v2)

    # Nothing deleted: v1's chunks are still stored, v2 has none ("Not searchable yet")...
    assert _chunk_texts(v1.document.id) == V1
    assert _chunk_texts(v2.document.id) == []
    # ...and v1 is inactive, so neither half of search returns them.
    found = PgChunkSearch(SessionLocal).search(
        np.array(fake_embedding(V1[0], EMBEDDING_DIM), dtype=np.float32),
        "vanishing gradients LSTMs gated", str(owner), top_k=10,
    )
    assert found.vector == [] and found.keyword == []


def test_reuploading_after_a_failed_changed_upload_clears_the_old_chunks(
    tmp_path: Path, users: Tuple[int, int], gemini: FakeGemini, parses_as: Callable[[List[str]], None]
) -> None:
    owner, _ = users
    storage = LocalFileStorage(tmp_path)
    parses_as(V1)
    v1 = _upload(storage, owner, b"v1")
    _index(v1)
    parses_as(V2)
    v2 = _upload(storage, owner, b"v2")
    gemini.embeddings_down = True
    with pytest.raises(EmbeddingError):
        _index(v2)
    gemini.embeddings_down = False

    again = _upload(storage, owner, b"v2")
    result = _index(again)

    assert again.status == "reindexed" and again.superseded_document_ids == (v1.document.id,)
    assert (result.embeddings_reused, result.texts_embedded) == (2, 1)
    assert _chunk_texts(v1.document.id) == []
    assert _chunk_texts(v2.document.id) == V2
