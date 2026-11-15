"""Day 15: search runs over document_chunks in Postgres (I4, I1, I2) and indexing never stores a
blank chunk or a zero vector.

Runs on the suite's database. Every test makes its own users (unique emails) and deletes them at
the end; ON DELETE CASCADE takes their documents and chunks with them.
"""
import hashlib
import uuid
from typing import Callable, Iterator, List

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document, User
from app.db.models.document_chunk import EMBEDDING_DIMENSIONS
from app.db.repositories import chunks as chunks_repo
from app.db.repositories.chunks import NewChunk
from app.db.session import SessionLocal
from app.ingestion.models import DocumentChunk
from app.retrieval.embeddings import EMBEDDING_DIM, EmbeddingError, EmbeddingService
from app.retrieval.pg_chunk_search import Candidates, PgChunkSearch
from app.retrieval.retrieval_service import RetrievalService
from app.services import indexing_service as indexing_module
from app.services.caches.query_cache import QueryCache
from app.services.caches.web_cache import WebCache
from app.services.indexing_service import IndexingService
from tests.conftest import SAMPLES_DIR
from tests.fakes import FakeGemini, FakeGenaiClient, FakeRedis

QUERY = "recurrent networks vanishing gradients"


def direction(x: float, y: float) -> np.ndarray:
    """A unit vector in the embedding space that points (x, y) in its first two dimensions."""
    vector = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    vector[:2] = (x, y)
    return vector / np.linalg.norm(vector)


QUERY_VECTOR = direction(1.0, 0.0)


class QueryEmbedder:
    def embed_texts(self, texts: List[str]) -> np.ndarray:
        return np.stack([QUERY_VECTOR for _ in texts])


@pytest.fixture
def make_document() -> Iterator[Callable[..., Document]]:
    """make_document([(text, vector), …]) → a committed new user's document; deleted afterwards."""
    user_ids: List[int] = []

    def make(texts_and_vectors: List[tuple], is_active: bool = True, file_name: str = "notes.pdf") -> Document:
        with SessionLocal() as db:
            user = User(email=f"chunks-{uuid.uuid4().hex[:12]}@example.com")
            db.add(user)
            db.flush()
            user_ids.append(user.id)
            doc = Document(user_id=user.id, file_name=file_name, file_path="k", file_hash="h",
                           version=1, is_active=is_active)
            db.add(doc)
            db.flush()
            add_chunks(db, doc, texts_and_vectors)
            db.commit()
            db.refresh(doc)
            db.expunge(doc)
            return doc

    yield make
    with SessionLocal() as db:
        for user_id in user_ids:
            user = db.get(User, user_id)
            if user is not None:
                db.delete(user)
        db.commit()


def add_chunks(db: Session, doc: Document, texts_and_vectors: List[tuple]) -> None:
    chunks_repo.insert_many(db, doc.user_id, [
        NewChunk(
            document_id=doc.id, document_version=doc.version, page=page, chunk_index=0, text=text,
            content_hash=hashlib.sha256(text.encode()).hexdigest(), embedding=vector,
            metadata={"doc_type": "pdf", "subject_tags": None},
        )
        for page, (text, vector) in enumerate(texts_and_vectors, start=1)
    ])


def search(doc: Document, keyword_query: str = QUERY, top_k: int = 5) -> Candidates:
    return PgChunkSearch(SessionLocal).search(QUERY_VECTOR, keyword_query, str(doc.user_id), top_k)


def test_embedding_size_matches_the_column() -> None:
    assert EMBEDDING_DIM == EMBEDDING_DIMENSIONS


# --- vector half ------------------------------------------------------------------------------

def test_nearest_chunk_first_and_the_score_is_cosine_similarity(make_document: Callable[..., Document]) -> None:
    doc = make_document([
        ("far", direction(-1.0, 0.2)), ("near", direction(1.0, 0.05)), ("middle", direction(0.5, 0.5)),
    ])

    vector = search(doc).vector

    assert [r["text"] for r in vector] == ["near", "middle", "far"]
    cosine = float(np.dot(QUERY_VECTOR, direction(1.0, 0.05)))
    # halfvec stores float16: ~3 significant digits, far finer than the gaps between chunks.
    assert vector[0]["score"] == pytest.approx(cosine, abs=1e-3)


def test_results_keep_the_metadata_shape_citations_and_parent_expansion_read(
    make_document: Callable[..., Document],
) -> None:
    doc = make_document([("near", direction(1.0, 0.0))], file_name="DL_Unit5_RNN.pdf")

    meta = search(doc).vector[0]["metadata"]

    assert meta["file_name"] == "DL_Unit5_RNN.pdf"
    assert meta["page_num"] == 1
    assert meta["extra_metadata"]["document_id"] == doc.id
    assert meta["user_id"] == str(doc.user_id)
    assert meta["doc_type"] == "pdf"


def test_a_minority_user_still_gets_top_k_of_their_own_chunks(make_document: Callable[..., Document]) -> None:
    # I1: FAISS over-fetched top_k·5 across all users and filtered afterwards, so a user whose chunks
    # were outranked by 25+ of someone else's got fewer than top_k. The filter is now in the query.
    make_document([(f"other {i}", direction(1.0, 0.001 * i)) for i in range(40)])
    small = make_document([(f"mine {i}", direction(-1.0, 0.1 * (i + 1))) for i in range(5)])

    vector = search(small, top_k=5).vector

    assert len(vector) == 5
    assert all(r["text"].startswith("mine") for r in vector)


def test_an_inactive_version_is_never_returned(make_document: Callable[..., Document]) -> None:
    old = make_document([("old version", direction(1.0, 0.0))], is_active=False)

    assert search(old).vector == []
    assert search(old, keyword_query="old version").keyword == []


# --- keyword half -----------------------------------------------------------------------------

def test_keyword_search_matches_any_term_with_stemming(make_document: Callable[..., Document]) -> None:
    doc = make_document([
        ("Recurrent networks suffer from vanishing gradients.", direction(1.0, 0.0)),
        ("The French Revolution began in 1789.", direction(0.0, 1.0)),
    ])

    # plainto_tsquery alone would AND every term ("brain" is in no chunk) and return nothing.
    keyword = search(doc, keyword_query="How do neural networks in the brain learn?").keyword

    assert [r["text"] for r in keyword] == ["Recurrent networks suffer from vanishing gradients."]
    assert keyword[0]["score"] > 0


def test_a_stop_word_only_query_finds_nothing_instead_of_failing(make_document: Callable[..., Document]) -> None:
    doc = make_document([("Recurrent networks.", direction(1.0, 0.0))])

    assert search(doc, keyword_query="what is the").keyword == []
    assert search(doc, keyword_query="   ").keyword == []


def test_exact_ties_in_vector_search_come_back_in_id_order(make_document: Callable[..., Document]) -> None:
    # Day 16: repeated slides have identical vectors; their order must not change from run to run.
    doc = make_document([
        ("Agenda (repeated slide)", direction(1.0, 0.0)), ("Closer than the ties", direction(1.0, 0.0)),
        ("Agenda (repeated slide) again", direction(1.0, 0.0)), ("Far away", direction(0.0, 1.0)),
    ])

    with SessionLocal() as db:
        hits = chunks_repo.vector_search(db, doc.user_id, QUERY_VECTOR, top_k=4)

    tied = [h for h in hits if h.score == pytest.approx(1.0, abs=1e-3)]
    assert len(tied) == 3
    assert [h.id for h in tied] == sorted(h.id for h in tied)
    assert hits[-1].text == "Far away"


# --- hybrid, through RetrievalService ---------------------------------------------------------

def test_nearest_chunk_ranks_first_after_fusion(make_document: Callable[..., Document]) -> None:
    # B8's check, now on pgvector: a higher-is-better score must stay higher-is-better through fusion.
    doc = make_document([
        (f"far {QUERY}", direction(-1.0, 0.2)), (f"near {QUERY}", direction(1.0, 0.05)),
        (f"middle {QUERY}", direction(0.5, 0.5)),
    ])
    redis_stub = FakeRedis()
    service = RetrievalService(
        QueryEmbedder(), PgChunkSearch(SessionLocal), QueryCache(redis_stub), WebCache(redis_stub),  # type: ignore[arg-type]
        web_search_enabled=False, l1_cache_enabled=False, vector_weight=1.0, keyword_weight=0.0,
    )

    result = service.hybrid_retrieve(QUERY, str(doc.user_id), 0, top_k=3, rerank_top_k=3)

    assert [r["text"].split()[0] for r in result["results"]] == ["near", "middle", "far"]
    assert result["results"][0]["score"] == pytest.approx(1.0)  # min-max: the nearest normalizes to 1


# --- delete -----------------------------------------------------------------------------------

def test_deleting_a_document_deletes_its_chunks(make_document: Callable[..., Document]) -> None:
    doc = make_document([("a", direction(1.0, 0.0)), ("b", direction(0.0, 1.0))])

    with SessionLocal() as db:
        db.delete(db.get(Document, doc.id))
        db.commit()
        remaining = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id))

    assert remaining == 0


# --- indexing ---------------------------------------------------------------------------------

def _indexing() -> IndexingService:
    return IndexingService(EmbeddingService(FakeGenaiClient()))  # type: ignore[arg-type]


def _index(service: IndexingService, doc: Document, file_path: str) -> int:
    with SessionLocal() as db:
        result = service.index_document(
            db, file_path=file_path, user_id=doc.user_id, document_id=doc.id,
            document_version=doc.version, file_name=doc.file_name,
        )
        db.commit()
        return result.chunks_indexed


def _stored(doc: Document) -> List[Chunk]:
    with SessionLocal() as db:
        return list(db.scalars(select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.id)))


def test_indexing_a_pdf_stores_every_chunk_with_a_unit_vector(
    make_document: Callable[..., Document], gemini: FakeGemini
) -> None:
    doc = make_document([])

    count = _index(_indexing(), doc, str(SAMPLES_DIR / "samples.pdf"))

    stored = _stored(doc)
    assert count == len(stored) > 0
    assert all(c.text.strip() and c.content_hash == hashlib.sha256(c.text.encode()).hexdigest() for c in stored)
    assert all(np.linalg.norm(np.asarray(c.embedding)) == pytest.approx(1.0, abs=1e-2) for c in stored)


def test_reindexing_replaces_the_documents_chunks(make_document: Callable[..., Document], gemini: FakeGemini) -> None:
    doc = make_document([])
    service = _indexing()

    first = _index(service, doc, str(SAMPLES_DIR / "samples.pdf"))
    second = _index(service, doc, str(SAMPLES_DIR / "samples.pdf"))

    assert first == second == len(_stored(doc))


def test_blank_chunks_are_skipped_not_embedded(
    make_document: Callable[..., Document], gemini: FakeGemini, monkeypatch: pytest.MonkeyPatch
) -> None:
    # B10: image-only PPTX slides produce empty chunks; the API rejects them and the table refuses them.
    doc = make_document([])
    parsed = [
        DocumentChunk(id=str(i), text=text, file_name="deck.pptx", page_num=i, chunk_index=0, doc_type="pptx",
                      extra_metadata={"document_id": doc.id, "slide_title": "t"})
        for i, text in enumerate(["", "   \n", "\x00", "Slide with real text\x00."], start=1)
    ]
    monkeypatch.setattr(indexing_module, "build_chunks_for_file", lambda *args, **kwargs: parsed)

    with SessionLocal() as db:
        result = _indexing().index_document(
            db, file_path="deck.pptx", user_id=doc.user_id, document_id=doc.id, document_version=1, file_name="deck.pptx",
        )
        db.commit()

    assert (result.chunks_indexed, result.blank_chunks_skipped) == (1, 3)
    assert gemini.embed_calls == 1
    (stored,) = _stored(doc)
    assert stored.text == "Slide with real text."  # NUL removed: Postgres text can't hold it
    assert stored.chunk_metadata == {"doc_type": "pptx", "subject_tags": None, "slide_title": "t"}


def test_a_failed_embedding_writes_nothing_and_keeps_the_old_chunks(
    make_document: Callable[..., Document], gemini: FakeGemini
) -> None:
    doc = make_document([])
    service = _indexing()
    before = _index(service, doc, str(SAMPLES_DIR / "samples.pdf"))

    gemini.embeddings_down = True  # past every retry, unlike one 429 (Day 16)
    with pytest.raises(EmbeddingError), SessionLocal() as db:
        # Same file: with reuse (CO3) it would make no call at all, so force the re-embed.
        service.index_document(
            db, file_path=str(SAMPLES_DIR / "samples.pdf"), user_id=doc.user_id, document_id=doc.id,
            document_version=doc.version, file_name=doc.file_name, reuse_embeddings=False,
        )

    assert len(_stored(doc)) == before


def test_embedding_service_raises_instead_of_returning_a_zero_vector(gemini: FakeGemini) -> None:
    gemini.fail_embedding_at = 1

    with pytest.raises(EmbeddingError, match="batch 1 of 1"):
        EmbeddingService(FakeGenaiClient(), max_attempts=1).embed_texts(["a", "b"])  # type: ignore[arg-type]
