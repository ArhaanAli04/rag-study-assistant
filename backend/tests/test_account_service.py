"""B1: deleting an account removes all of that user's data and nothing of anyone else's.

Runs on the suite's Postgres database, so foreign keys are enforced and a delete in the wrong
order fails here. Users get database-assigned ids and unique emails, because the database is
shared with the rest of the suite; every assertion is scoped to the users a test created.
Since Day 15 the search chunks are rows too (document_chunks), deleted in the same transaction.
"""
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

import numpy as np
import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from app.services.account_service import delete_user_account
from app.db.models.concept_map import ConceptMap, ConceptMapNode
from app.db.models import Chunk, Document, FailedQuery, Message, Session as ChatSession, User
from app.db.repositories import chunks as chunks_repo
from app.db.repositories.chunks import NewChunk
from app.ingestion.upload_storage import new_upload_path
from app.retrieval.embeddings import EMBEDDING_DIM


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


def _unit_vector() -> np.ndarray:
    vector = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    vector[0] = 1.0
    return vector


def _seed_user(db: DbSession, root: Path, shared_legacy: str) -> Tuple[int, Dict[str, Path]]:
    user = User(email=f"account-{uuid.uuid4().hex[:12]}@example.com")
    db.add(user)
    db.flush()
    own = new_upload_path(root, user.id, ".pdf")
    own.write_bytes(b"%PDF own")
    private_legacy = root / f"private_{user.id}.pdf"
    private_legacy.write_bytes(b"%PDF legacy")
    documents = [
        Document(user_id=user.id, file_name=path.name, file_path=str(path), file_hash="h", version=1, is_active=True)
        for path in (own, private_legacy, Path(shared_legacy))
    ]
    db.add_all(documents)
    db.flush()
    chunks_repo.insert_many(db, user.id, [
        NewChunk(document_id=doc.id, document_version=1, page=1, chunk_index=i, text=f"recurrent networks {i}",
                 content_hash="h", embedding=_unit_vector(), metadata={})
        for doc in documents[:1] for i in range(2)
    ])
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


def _count(db: DbSession, model: Any, user_id: int) -> int:
    return db.query(func.count()).select_from(model).filter(model.user_id == user_id).scalar()


def test_deleting_an_account_removes_everything_of_that_user_only(db: DbSession, root: Path) -> None:
    root.mkdir(parents=True)
    shared = root / "DL_Unit5_RNN.pdf"
    shared.write_bytes(b"%PDF shared by A and B before G7")
    a, files_a = _seed_user(db, root, str(shared))
    b, files_b = _seed_user(db, root, str(shared))
    semantic_cache, l1 = FakeSemanticCache(a, b), FakeL1Cache(a, b)

    summary = delete_user_account(
        db, db.get(User, a), semantic_cache=semantic_cache, retrieval_cache=l1, upload_root=root,
    )

    for model in (Document, ChatSession, Message, FailedQuery, ConceptMap, Chunk):
        assert _count(db, model, a) == 0, model.__tablename__
        assert _count(db, model, b) > 0, model.__tablename__
    assert db.get(User, a) is None and db.get(User, b) is not None
    remaining_nodes = db.query(ConceptMapNode).join(ConceptMap).filter(ConceptMap.user_id.in_([a, b])).all()
    assert [n.concept_map.user_id for n in remaining_nodes] == [b]

    assert not (root / str(a)).exists()
    assert not files_a["private_legacy"].exists()
    assert shared.exists(), "B's document still references the shared pre-G7 file"
    assert files_b["own"].exists() and files_b["private_legacy"].exists()

    assert semantic_cache.keys == {f"semantic_cache:{b}"}
    assert list(l1.entries) == [(str(b), "q", 0)]

    assert summary.documents == 3
    assert summary.sessions == 1
    assert summary.messages == 2
    assert summary.concept_maps == 1
    assert summary.failed_queries == 1
    assert summary.files_removed == 2
    assert summary.index_entries_removed == 2  # the user's document_chunks rows


def test_the_schema_cascades_a_users_rows_whatever_the_code_path(db: DbSession, root: Path) -> None:
    # Day 15: a plain DELETE of the user (no children-first code) must not fail or leave rows behind.
    root.mkdir(parents=True)
    a, _ = _seed_user(db, root, str(root / "unused.pdf"))

    db.query(User).filter(User.id == a).delete(synchronize_session=False)
    db.commit()

    for model in (Document, ChatSession, Message, FailedQuery, ConceptMap, Chunk):
        assert _count(db, model, a) == 0, model.__tablename__
