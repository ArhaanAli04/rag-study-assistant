"""B1: deleting an account removes all of that user's data and nothing of anyone else's."""
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session as DbSession, sessionmaker
from sqlalchemy.pool import StaticPool

from app.services.account_service import delete_user_account
from app.db.models.concept_map import ConceptMap, ConceptMapNode
from app.db.base import Base
from app.db.models import Document, FailedQuery, Message, Session as ChatSession, User
from app.retrieval.keyword_index import BM25KeywordIndex
from app.ingestion.models import DocumentChunk
from app.ingestion.upload_storage import new_upload_path
from app.retrieval.vector_store import FaissVectorStore

A, B = 1, 2
DIM = 4


class FakeSemanticCache:
    def __init__(self) -> None:
        self.keys = {f"semantic_cache:{A}", f"semantic_cache:{B}"}

    def clear_user(self, user_id: int) -> None:
        self.keys.discard(f"semantic_cache:{user_id}")


class FakeL1Cache:
    def __init__(self) -> None:
        self.entries: Dict[Tuple[str, str, int], Any] = {
            (str(A), "q", 0): {}, (str(B), "q", 0): {},
        }

    def l1_cache_purge_user(self, user_id: str) -> int:
        stale = [k for k in self.entries if k[0] == user_id]
        for key in stale:
            del self.entries[key]
        return len(stale)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return Path("uploads")


@pytest.fixture
def db() -> DbSession:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session


def _chunk(user_id: int, text: str) -> DocumentChunk:
    return DocumentChunk(
        id=f"{user_id}-{text}", text=text, file_name="notes.pdf", page_num=1,
        chunk_index=0, doc_type="pdf", subject_tags=None, extra_metadata={"document_id": user_id},
    )


def _seed_user(db: DbSession, root: Path, user_id: int, shared_legacy: str) -> Dict[str, Path]:
    db.add(User(id=user_id, email=f"user{user_id}@example.com"))
    own = new_upload_path(root, user_id, ".pdf")
    own.write_bytes(b"%PDF own")
    private_legacy = root / f"private_{user_id}.pdf"
    private_legacy.write_bytes(b"%PDF legacy")
    for path in (own, private_legacy, Path(shared_legacy)):
        db.add(Document(user_id=user_id, file_name=path.name, file_path=str(path),
                        file_hash="h", version=1, is_active=True))
    chat = ChatSession(user_id=user_id, title="chat")
    db.add(chat)
    db.flush()
    db.add_all([
        Message(user_id=user_id, session_id=chat.id, role="user", content="q"),
        Message(user_id=user_id, session_id=chat.id, role="assistant", content="a"),
        FailedQuery(user_id=user_id, session_id=chat.id, query="q", reason="low_confidence"),
    ])
    concept_map = ConceptMap(user_id=user_id, topic="RNN")
    db.add(concept_map)
    db.flush()
    db.add(ConceptMapNode(map_id=concept_map.id, node_id="n1", label="LSTM"))
    db.commit()
    return {"own": own, "private_legacy": private_legacy}


def _indexes() -> Tuple[FaissVectorStore, BM25KeywordIndex]:
    store = FaissVectorStore(embedding_dim=DIM)
    bm25 = BM25KeywordIndex()
    chunks = [_chunk(A, "recurrent networks"), _chunk(B, "recurrent networks")]
    store.add_embeddings(np.ones((1, DIM), dtype=np.float32), [chunks[0]], user_id=str(A))
    store.add_embeddings(np.ones((1, DIM), dtype=np.float32), [chunks[1]], user_id=str(B))
    bm25.add_documents([
        {"text": c.text, "metadata": {"user_id": str(uid), "id": c.id}}
        for uid, c in ((A, chunks[0]), (B, chunks[1]))
    ])
    return store, bm25


def _count(db: DbSession, model: Any, user_id: int) -> int:
    return db.query(func.count()).select_from(model).filter(model.user_id == user_id).scalar()


def test_deleting_an_account_removes_everything_of_that_user_only(db: DbSession, root: Path) -> None:
    root.mkdir(parents=True)
    shared = root / "DL_Unit5_RNN.pdf"
    shared.write_bytes(b"%PDF shared by A and B before G7")
    files_a = _seed_user(db, root, A, str(shared))
    files_b = _seed_user(db, root, B, str(shared))
    store, bm25 = _indexes()
    semantic_cache, l1 = FakeSemanticCache(), FakeL1Cache()

    summary = delete_user_account(
        db, db.get(User, A), indexes=[store, bm25], semantic_cache=semantic_cache,
        retrieval_cache=l1, upload_root=root,
    )

    for model in (Document, ChatSession, Message, FailedQuery, ConceptMap):
        assert _count(db, model, A) == 0, model.__tablename__
        assert _count(db, model, B) > 0, model.__tablename__
    assert db.get(User, A) is None and db.get(User, B) is not None
    remaining_nodes = db.query(ConceptMapNode).join(ConceptMap).all()
    assert [n.concept_map.user_id for n in remaining_nodes] == [B]
    assert db.query(ConceptMapNode).count() == 1

    assert not (root / str(A)).exists()
    assert not files_a["private_legacy"].exists()
    assert shared.exists(), "B's document still references the shared pre-G7 file"
    assert files_b["own"].exists() and files_b["private_legacy"].exists()

    query = np.ones(DIM, dtype=np.float32)
    assert [m["user_id"] for _, m in store.search(query, top_k=5)] == [str(B)]
    assert [r["metadata"]["user_id"] for r in bm25.search("recurrent", top_k=5)] == [str(B)]
    assert semantic_cache.keys == {f"semantic_cache:{B}"}
    assert list(l1.entries) == [(str(B), "q", 0)]

    assert summary.documents == 3
    assert summary.sessions == 1
    assert summary.messages == 2
    assert summary.concept_maps == 1
    assert summary.failed_queries == 1
    assert summary.files_removed == 2
    assert summary.index_entries_removed == 2


def test_a_new_account_reusing_the_id_sees_no_old_chunks(db: DbSession, root: Path) -> None:
    # SQLite hands out max(id)+1, so a deleted highest id comes back for the next sign-up.
    root.mkdir(parents=True)
    _seed_user(db, root, A, str(root / "unused.pdf"))
    store, bm25 = _indexes()
    delete_user_account(
        db, db.get(User, A), indexes=[store, bm25], semantic_cache=FakeSemanticCache(),
        retrieval_cache=FakeL1Cache(), upload_root=root,
    )

    filters = {"user_id": str(A)}
    assert store.search(np.ones(DIM, dtype=np.float32), top_k=5, filters=filters) == []
    assert bm25.search("recurrent", top_k=5, filters=filters) == []


def test_bm25_search_skips_tombstoned_entries() -> None:
    bm25 = BM25KeywordIndex()
    bm25.add_documents([
        {"text": "gradient descent", "metadata": {"user_id": "1"}},
        {"text": "gradient clipping", "metadata": {"user_id": "2"}},
    ])

    assert bm25.mark_deleted_by_user("1") == 1
    assert bm25.mark_deleted_by_user("1") == 0
    results: List[Dict[str, Any]] = bm25.search("gradient", top_k=5)
    assert [r["metadata"]["user_id"] for r in results] == ["2"]
