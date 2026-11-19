"""Day 18: a chat searches only its project's documents, and no cache crosses projects.

Two layers:
- the search itself (PgChunkSearch on the suite's Postgres): two projects of one user retrieve
  disjointly in both halves, vector and keyword;
- the whole chat (the real app, fake Gemini): a chat in project A never cites project B's document,
  the same question in B is not replayed from A (L1 or semantic cache), and once B's document is
  moved into A, A's chat cites it on the next turn instead of replaying its old answer.
"""
import hashlib
import uuid
from typing import Any, Dict, Iterator, List, Set, Tuple

import numpy as np
import pytest
from sqlalchemy import event

from app.db.models import Document, Project, User
from app.db.repositories import chunks as chunks_repo
from app.db.repositories.chunks import NewChunk
from app.db.scope import DocumentScope
from app.db.session import SessionLocal, engine
from app.generation.llm_client import INSTRUCTIONS_CLOSE, INSTRUCTIONS_OPEN
from app.retrieval.embeddings import EMBEDDING_DIM
from app.retrieval.pg_chunk_search import PgChunkSearch
from tests.conftest import Account
from tests.fakes import FakeGemini
from tests.test_api_smoke import QUESTION, SAMPLE_PDF, assert_contract, parse_sse
from tests.test_projects_api import create_project, upload_into

TEXT = "Recurrent networks suffer from vanishing gradients."


# --- the search: PgChunkSearch with each scope -----------------------------------------------------

def _unit_vector() -> np.ndarray:
    vector = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    vector[0] = 1.0
    return vector


@pytest.fixture
def three_documents() -> Iterator[Tuple[int, int, int]]:
    """A user with project A's, project B's and an unassigned document, all with the same chunk text
    and vector, so only the scope can tell them apart. Yields (user_id, project A id, project B id)."""
    with SessionLocal() as db:
        user = User(email=f"scope-{uuid.uuid4().hex[:12]}@example.com")
        db.add(user)
        db.flush()
        project_a = Project(user_id=user.id, name="A")
        project_b = Project(user_id=user.id, name="B")
        db.add_all([project_a, project_b])
        db.flush()
        for name, project_id in (("a.pdf", project_a.id), ("b.pdf", project_b.id), ("loose.pdf", None)):
            document = Document(user_id=user.id, project_id=project_id, file_name=name, file_path="k",
                                file_hash=name, version=1, is_active=True)
            db.add(document)
            db.flush()
            chunks_repo.insert_many(db, user.id, [NewChunk(
                document_id=document.id, document_version=1, page=1, chunk_index=0, text=TEXT,
                content_hash=hashlib.sha256(TEXT.encode()).hexdigest(), embedding=_unit_vector(), metadata={},
            )])
        db.commit()
        ids = (user.id, project_a.id, project_b.id)
    yield ids
    with SessionLocal() as db:
        db.delete(db.get(User, ids[0]))
        db.commit()


def _found(user_id: int, scope: DocumentScope) -> Tuple[Set[str], Set[str]]:
    candidates = PgChunkSearch(SessionLocal).search(_unit_vector(), "recurrent networks", str(user_id), 10, scope)
    return (
        {r["metadata"]["file_name"] for r in candidates.vector},
        {r["metadata"]["file_name"] for r in candidates.keyword},
    )


def test_two_projects_of_one_user_retrieve_disjointly(three_documents: Tuple[int, int, int]) -> None:
    user_id, project_a, project_b = three_documents

    assert _found(user_id, DocumentScope.project(project_a)) == ({"a.pdf"}, {"a.pdf"})
    assert _found(user_id, DocumentScope.project(project_b)) == ({"b.pdf"}, {"b.pdf"})
    # A chat outside any project sees only unassigned documents (Decision 1A).
    assert _found(user_id, DocumentScope.unassigned()) == ({"loose.pdf"}, {"loose.pdf"})
    # "all" (eval, POST /search, concept maps until Day 20) is what search did before Day 18.
    everything = {"a.pdf", "b.pdf", "loose.pdf"}
    assert _found(user_id, DocumentScope.all()) == (everything, everything)


def test_another_users_project_id_finds_nothing(three_documents: Tuple[int, int, int]) -> None:
    # Defence in depth below the routes' 404: the user filter stays in the query whatever the scope.
    user_id, project_a, _ = three_documents
    with SessionLocal() as db:
        stranger = User(email=f"stranger-{uuid.uuid4().hex[:12]}@example.com")
        db.add(stranger)
        db.commit()
        stranger_id = stranger.id
    try:
        assert _found(stranger_id, DocumentScope.project(project_a)) == (set(), set())
    finally:
        with SessionLocal() as db:
            db.delete(db.get(User, stranger_id))
            db.commit()


# --- the whole chat -------------------------------------------------------------------------------

def _ask(client: Any, account: Account, project_id: int | None = None, session_id: int = 0) -> Dict[str, Any]:
    params: Dict[str, Any] = {"query": QUESTION, "session_id": session_id, "mode": "quick", "token": account.token}
    if project_id is not None:
        params["project_id"] = project_id
    response = client.get("/chat/stream", params=params)
    assert response.status_code == 200, response.text
    return assert_contract(parse_sse(response.text))


def _cited(turn: Dict[str, Any]) -> Set[str]:
    return {s.get("file_name") for s in turn["metadata"]["sources"] if s.get("file_name")}


@pytest.fixture
def two_projects(client: Any, account: Account) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Project A holds a.pdf, project B holds b.pdf: the same bytes (QUESTION's words are in both, and
    B's chunks reuse A's vectors), so only the project decides which one a chat may cite."""
    project_a, project_b = create_project(client, account, "A"), create_project(client, account, "B")
    pdf = SAMPLE_PDF.read_bytes()
    assert upload_into(client, account, project_a["id"], file_name="a.pdf", content=pdf).status_code == 200
    assert upload_into(client, account, project_b["id"], file_name="b.pdf", content=pdf).status_code == 200
    return project_a, project_b


def test_a_chat_in_project_a_never_cites_project_b_until_the_document_moves_in(
    client: Any, account: Account, gemini: FakeGemini, two_projects: Tuple[Dict[str, Any], Dict[str, Any]]
) -> None:
    project_a, project_b = two_projects

    first = _ask(client, account, project_a["id"])
    session_a = first["metadata"]["session_id"]
    assert _cited(first) == {"a.pdf"}

    # The same question again in A: a semantic-cache replay, still only A's file.
    replay = _ask(client, account, session_id=session_a)
    assert gemini.stream_calls == 1, "the repeated question in the same scope was a cached replay"
    assert _cited(replay) == {"a.pdf"}

    # The same question in B: neither the semantic cache nor the L1 ranking crosses projects.
    in_b = _ask(client, account, project_b["id"])
    assert gemini.stream_calls == 2, "B's chat answered fresh instead of replaying A's answer"
    assert _cited(in_b) == {"b.pdf"}

    # Move b.pdf into A. The next turn of A's chat must search again and cite it: the move bumped
    # doc_version, so neither cache may replay the answer from before the move.
    b_document = next(d for d in client.get("/documents", headers=account.headers).json() if d["filename"] == "b.pdf")
    moved = client.patch(f"/documents/{b_document['id']}", headers=account.headers, json={"project_id": project_a["id"]})
    assert moved.status_code == 200, moved.text

    after_move = _ask(client, account, session_id=session_a)
    assert gemini.stream_calls == 3, "the turn after the move was replayed from the cache"
    assert _cited(after_move) == {"a.pdf", "b.pdf"}

    # B's chat no longer sees it.
    assert _cited(_ask(client, account, session_id=in_b["metadata"]["session_id"])) == set()


def test_a_chat_outside_projects_sees_neither_project(
    client: Any, account: Account, gemini: FakeGemini, two_projects: Tuple[Dict[str, Any], Dict[str, Any]]
) -> None:
    upload_into(client, account, None, file_name="loose.pdf")

    assert _cited(_ask(client, account)) == {"loose.pdf"}


def test_project_instructions_reach_the_final_user_turn_and_editing_them_stops_replays(
    client: Any, account: Account, gemini: FakeGemini
) -> None:
    project = create_project(client, account, "DL", instructions="Answer in exactly three bullet points.")
    upload_into(client, account, project["id"])

    first = _ask(client, account, project["id"])
    final_turn = str(gemini.prompts[-1][-1])
    assert INSTRUCTIONS_OPEN in final_turn and INSTRUCTIONS_CLOSE in final_turn
    assert "Answer in exactly three bullet points." in final_turn
    # Earlier turns of the conversation never carry them.
    assert all("three bullet points" not in str(turn) for turn in gemini.prompts[-1][:-1])

    edited = client.patch(f"/projects/{project['id']}", headers=account.headers,
                          json={"instructions": "Answer in one sentence."})
    assert edited.status_code == 200

    _ask(client, account, session_id=first["metadata"]["session_id"])
    assert gemini.stream_calls == 2, "an answer built under the old instructions was replayed"
    assert "Answer in one sentence." in str(gemini.prompts[-1][-1])


def test_a_new_chat_in_a_project_costs_no_extra_query_for_its_instructions(
    client: Any, account: Account, gemini: FakeGemini, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The route's ownership check already loaded the project into the request's session; the turn
    # reads its instructions from there, not with a second SELECT.
    project = create_project(client, account, "DL", instructions="Be brief.")
    statements: List[str] = []

    def record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        _ask(client, account, project["id"])
    finally:
        event.remove(engine, "before_cursor_execute", record)

    project_reads = [s for s in statements if "FROM projects" in s and "WHERE projects.id" in s]
    assert len(project_reads) == 1, project_reads
