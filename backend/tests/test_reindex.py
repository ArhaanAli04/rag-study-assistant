"""The reindex script (Day 16, Decision 4A): dry run by default, the upload path's IndexingService,
reuse of stored embeddings, missing files reported, doc_version bumped with each document's commit.

Always scoped with user_id: the suite's database is shared, and other tests' documents must not be
reindexed here.
"""
import uuid
from pathlib import Path
from typing import Callable, Iterator, List, Tuple

import pytest
from sqlalchemy import func, select

from app.db.models import Chunk, Document, User
from app.db.session import SessionLocal
from app.ingestion.models import DocumentChunk
from app.ingestion.upload_storage import LocalFileStorage, new_upload_key
from app.retrieval.embeddings import EmbeddingService
from app.services import indexing_service as indexing_module
from app.services.indexing_service import IndexingService
from scripts.reindex_all import ReindexReport, reindex
from tests.fakes import FakeGemini, FakeGenaiClient

TEXTS = ["Backpropagation through time unrolls the network.", "Gradient clipping caps the norm."]


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path)


@pytest.fixture
def owner() -> Iterator[int]:
    with SessionLocal() as db:
        user = User(email=f"reindex-{uuid.uuid4().hex[:12]}@example.com")
        db.add(user)
        db.commit()
        user_id = user.id
    yield user_id
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).delete()
        db.commit()


@pytest.fixture(autouse=True)
def parsed_as_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [
        DocumentChunk(id=str(i), text=t, file_name="rnn.pdf", page_num=i, chunk_index=0, doc_type="pdf")
        for i, t in enumerate(TEXTS, start=1)
    ]
    monkeypatch.setattr(indexing_module, "build_chunks_for_file", lambda *args, **kwargs: list(chunks))


@pytest.fixture
def make_document(storage: LocalFileStorage, owner: int) -> Callable[..., int]:
    def make(file_name: str = "rnn.pdf", store_file: bool = True) -> int:
        key = new_upload_key(owner, ".pdf")
        if store_file:
            storage.put(key, b"%PDF-1.4 notes")
        with SessionLocal() as db:
            doc = Document(user_id=owner, file_name=file_name, file_path=key, file_hash=uuid.uuid4().hex,
                           version=1, is_active=True)
            db.add(doc)
            db.commit()
            return doc.id

    return make


def _run(storage: LocalFileStorage, owner: int, **options: bool) -> ReindexReport:
    service = IndexingService(EmbeddingService(FakeGenaiClient()))  # type: ignore[arg-type]
    return reindex(SessionLocal, storage, service, user_id=owner, **options)


def _chunks(document_id: int) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id))


def _doc_version(user_id: int) -> int:
    with SessionLocal() as db:
        return db.get(User, user_id).doc_version


def _actions(report: ReindexReport) -> List[Tuple[int, str]]:
    return [(r.document_id, r.action) for r in report.rows]


def test_a_dry_run_lists_documents_without_chunks_and_writes_nothing(
    storage: LocalFileStorage, owner: int, make_document: Callable[..., int], gemini: FakeGemini
) -> None:
    document_id = make_document()

    report = _run(storage, owner)

    assert _actions(report) == [(document_id, "would index")]
    assert _chunks(document_id) == 0 and _doc_version(owner) == 0
    assert gemini.embed_calls == 0


def test_apply_indexes_the_document_and_bumps_doc_version_with_it(
    storage: LocalFileStorage, owner: int, make_document: Callable[..., int], gemini: FakeGemini
) -> None:
    document_id = make_document()

    report = _run(storage, owner, apply=True)

    (row,) = report.rows
    assert (row.action, row.chunks_after, row.texts_embedded) == ("indexed", 2, 2)
    assert _chunks(document_id) == 2
    assert _doc_version(owner) == 1


def test_a_missing_file_is_reported_and_skipped(
    storage: LocalFileStorage, owner: int, make_document: Callable[..., int], gemini: FakeGemini
) -> None:
    # v0.2.2's production rows: the row survived, Render's disk did not.
    document_id = make_document(store_file=False)

    report = _run(storage, owner, apply=True)

    assert _actions(report) == [(document_id, "skipped: file missing")]
    assert report.failed == 0 and _doc_version(owner) == 0


def test_documents_with_chunks_are_left_alone_unless_all(
    storage: LocalFileStorage, owner: int, make_document: Callable[..., int], gemini: FakeGemini
) -> None:
    document_id = make_document()
    _run(storage, owner, apply=True)

    assert _actions(_run(storage, owner, apply=True)) == [(document_id, "skipped: has chunks")]
    assert _actions(_run(storage, owner, all_documents=True)) == [(document_id, "would index")]


def test_reindexing_everything_again_reuses_every_embedding(
    storage: LocalFileStorage, owner: int, make_document: Callable[..., int], gemini: FakeGemini
) -> None:
    document_id = make_document()
    _run(storage, owner, apply=True)
    calls_before = gemini.embed_calls

    again = _run(storage, owner, all_documents=True, apply=True)

    (row,) = again.rows
    assert (row.action, row.embeddings_reused, row.texts_embedded) == ("indexed", 2, 0)
    assert gemini.embed_calls == calls_before
    assert _chunks(document_id) == 2


def test_re_embed_bypasses_reuse(
    storage: LocalFileStorage, owner: int, make_document: Callable[..., int], gemini: FakeGemini
) -> None:
    make_document()
    _run(storage, owner, apply=True)

    (row,) = _run(storage, owner, all_documents=True, re_embed=True, apply=True).rows

    assert (row.embeddings_reused, row.texts_embedded) == (0, 2)


class _ModelsOfAClosableClient:
    def __init__(self) -> None:
        self.closed = False
        self.calls = 0

    def embed_content(self, **kwargs: object) -> str:
        if self.closed:
            raise RuntimeError("Cannot send a request, as the client has been closed.")
        self.calls += 1
        return "embedded"


class _ClientThatClosesWhenCollected:
    """Like genai.Client (found live on Day 16): once nothing references it, it is garbage-collected
    and closes its HTTP client, and its .models can't send anything any more. .models holds no
    reference back to the client, so keeping only .models doesn't keep the client alive."""

    def __init__(self) -> None:
        self.models = _ModelsOfAClosableClient()

    def __del__(self) -> None:
        self.models.closed = True


def test_the_request_counter_keeps_the_whole_client_alive() -> None:
    import gc

    from scripts.reindex_all import _CountingClient

    counting = _CountingClient(_ClientThatClosesWhenCollected())
    gc.collect()

    assert counting.models.embed_content(model="m", contents=["a"]) == "embedded"
    assert counting.models.requests == 1


def test_an_embedding_outage_fails_that_document_and_writes_nothing(
    storage: LocalFileStorage, owner: int, make_document: Callable[..., int], gemini: FakeGemini
) -> None:
    document_id = make_document()
    gemini.embeddings_down = True

    report = _run(storage, owner, apply=True)

    assert _actions(report) == [(document_id, "failed: EmbeddingError")]
    assert report.failed == 1
    assert _chunks(document_id) == 0 and _doc_version(owner) == 0
