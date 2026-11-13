"""B1: deleting an account removes all of that user's data and nothing of anyone else's.

Runs on the suite's own database (SessionLocal: the temp SQLite file, or the Postgres _test
database in CI since Day 14), so foreign keys are enforced on Postgres and a delete in the wrong
order fails here. Users get database-assigned ids and unique emails, because the database is
shared with the rest of the suite; every assertion is scoped to the users a test created.
"""
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import numpy as np
import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from app.services.account_service import delete_user_account
from app.db.models.concept_map import ConceptMap, ConceptMapNode
from app.db.models import Document, FailedQuery, Message, Session as ChatSession, User
from app.retrieval.keyword_index import BM25KeywordIndex
from app.ingestion.models import DocumentChunk
from app.ingestion.upload_storage import new_upload_path
from app.retrieval.vector_store import FaissVectorStore

DIM = 4


class FakeSemanticCache:
    def __init__(self, *user_ids: int) -> None:
        self.keys = {f"semantic_cache:{user_id}" for user_id in user_ids}

    def clear_user(self, user_id: int) -> None:
        self.keys.discard(f"semantic_cache:{user_id}")


class FakeL1Cache:
    def __init__(self, *user_ids: int) -> None:
        self.entries: Dict[Tuple[str, str, int], Any] = {(str(user_id), "q", 0): {} for user_id in user_ids}

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
def db() -> Iterator[DbSession]:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        yield session


def _chunk(user_id: int, text: str) -> DocumentChunk:
    return DocumentChunk(
        id=f"{user_id}-{text}", text=text, file_name="notes.pdf", page_num=1,
        chunk_index=0, doc_type="pdf", subject_tags=None, extra_metadata={"document_id": user_id},
    )


def _seed_user(db: DbSession, root: Path, shared_legacy: str) -> Tuple[int, Dict[str, Path]]:
    user = User(email=f"account-{uuid.uuid4().hex[:12]}@example.com")
    db.add(user)
    db.flush()
    own = new_upload_path(root, user.id, ".pdf")
    own.write_bytes(b"%PDF own")
    private_legacy = root / f"private_{user.id}.pdf"
    private_legacy.write_bytes(b"%PDF legacy")
    for path in (own, private_legacy, Path(shared_legacy)):
        db.add(Document(user_id=user.id, file_name=path.name, file_path=str(path),
                        file_hash="h", version=1, is_active=True))
    chat = ChatSession(user_id=user.id, title="chat")
    db.add(chat)
    db.flush()
    db.add_all([
        Message(user_id=user.id, session_id=chat.id, role="user", content="q"),
        Message(user_id=user.id, session_id=chat.id, role="assistant", content="a"),
        FailedQuery(user_id=user.id, session_id=chat.id, query="q", reason="low_confidence"),
    ])
    concept_map = ConceptMap(user_id=user.id, topic="RNN")
    db.add(concept_map)
    db.flush()
    db.add(ConceptMapNode(map_id=concept_map.id, node_id="n1", label="LSTM"))
    db.commit()
    return user.id, {"own": own, "private_legacy": private_legacy}


def _indexes(a: int, b: int) -> Tuple[FaissVectorStore, BM25KeywordIndex]:
    store = FaissVectorStore(embedding_dim=DIM)
    bm25 = BM25KeywordIndex()
    chunks = [_chunk(a, "recurrent networks"), _chunk(b, "recurrent networks")]
    store.add_embeddings(np.ones((1, DIM), dtype=np.float32), [chunks[0]], user_id=str(a))
    store.add_embeddings(np.ones((1, DIM), dtype=np.float32), [chunks[1]], user_id=str(b))
    bm25.add_documents([
        {"text": c.text, "metadata": {"user_id": str(uid), "id": c.id}}
        for uid, c in ((a, chunks[0]), (b, chunks[1]))
    ])
    return store, bm25


def _count(db: DbSession, model: Any, user_id: int) -> int:
    return db.query(func.count()).select_from(model).filter(model.user_id == user_id).scalar()


def test_deleting_an_account_removes_everything_of_that_user_only(db: DbSession, root: Path) -> None:
    root.mkdir(parents=True)
    shared = root / "DL_Unit5_RNN.pdf"
    shared.write_bytes(b"%PDF shared by A and B before G7")
    a, files_a = _seed_user(db, root, str(shared))
    b, files_b = _seed_user(db, root, str(shared))
    store, bm25 = _indexes(a, b)
    semantic_cache, l1 = FakeSemanticCache(a, b), FakeL1Cache(a, b)

    summary = delete_user_account(
        db, db.get(User, a), indexes=[store, bm25], semantic_cache=semantic_cache,
        retrieval_cache=l1, upload_root=root,
    )

    for model in (Document, ChatSession, Message, FailedQuery, ConceptMap):
        assert _count(db, model, a) == 0, model.__tablename__
        assert _count(db, model, b) > 0, model.__tablename__
    assert db.get(User, a) is None and db.get(User, b) is not None
    remaining_nodes = db.query(ConceptMapNode).join(ConceptMap).filter(ConceptMap.user_id.in_([a, b])).all()
    assert [n.concept_map.user_id for n in remaining_nodes] == [b]

    assert not (root / str(a)).exists()
    assert not files_a["private_legacy"].exists()
    assert shared.exists(), "B's document still references the shared pre-G7 file"
    assert files_b["own"].exists() and files_b["private_legacy"].exists()

    query = np.ones(DIM, dtype=np.float32)
    assert [m["user_id"] for _, m in store.search(query, top_k=5)] == [str(b)]
    assert [r["metadata"]["user_id"] for r in bm25.search("recurrent", top_k=5)] == [str(b)]
    assert semantic_cache.keys == {f"semantic_cache:{b}"}
    assert list(l1.entries) == [(str(b), "q", 0)]

    assert summary.documents == 3
    assert summary.sessions == 1
    assert summary.messages == 2
    assert summary.concept_maps == 1
    assert summary.failed_queries == 1
    assert summary.files_removed == 2
    assert summary.index_entries_removed == 2


def test_a_new_account_reusing_the_id_sees_no_old_chunks(db: DbSession, root: Path) -> None:
    # SQLite hands out max(id)+1, so a deleted highest id comes back for the next sign-up (the B1
    # residual; Postgres sequences never reuse an id). The tombstones must hide the old chunks anyway.
    root.mkdir(parents=True)
    a, _ = _seed_user(db, root, str(root / "unused.pdf"))
    other = a + 1
    store, bm25 = _indexes(a, other)
    delete_user_account(
        db, db.get(User, a), indexes=[store, bm25], semantic_cache=FakeSemanticCache(a),
        retrieval_cache=FakeL1Cache(a), upload_root=root,
    )

    filters = {"user_id": str(a)}
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
