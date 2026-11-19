"""The event loop must never wait on blocking work (v0.3.1 hotfix).

Production runs one uvicorn worker. Before v0.3.1, `async def` routes ran sync DB, Gemini and Tavily
calls directly on the event loop, so while one chat turn or upload was working nothing else was
served, not even /health: Render's 5 s health check failed, the instance was restarted and open
chat streams were cut (3 of 15 turns in the v0.3.0 latency run).

Inside `with TestClient(app)` every request runs on one shared event loop, like one uvicorn worker,
so a request sent from a second thread waits exactly when production's /health would.

The same tests check that no pooled DB connection is held while slow external calls run: the
pool is 5 + 5 connections, and once requests run in parallel a connection held through minutes of
paced embedding would starve every other request.
"""
import inspect
import threading
import time
import uuid
from typing import Any, Callable, Dict, Iterator, List

import pytest
from fastapi.routing import APIRoute

from app.db.models import Document, User
from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.session import SessionLocal, engine
from app.services import document_service
from app.services.chat_pipeline import ChatPipeline
from app.services.indexing_service import PendingWrites
from tests.conftest import Account
from tests.fakes import FakeGemini
from tests.test_api_smoke import SAMPLE_PDF, assert_contract, chat, upload

SLOW_SECONDS = 3.0
# Render's health check gives up after 5 s; a free event loop answers in milliseconds.
HEALTH_BUDGET_SECONDS = 1.0

# Routes allowed to be `async def`: they await and never block. Everything else is a plain `def`,
# which FastAPI runs in its threadpool.
ASYNC_ROUTE_ALLOWLIST = {
    "/health",
    "/auth/logout",
    "/auth/google/login",
    "/auth/google/callback",
}


def health_time_while(client: Any, started: threading.Event, slow_request: Callable[[], Any]) -> tuple[float, Any]:
    """Run `slow_request` in a thread; once its fake slow call has started, time one /health.

    Returns (seconds /health took, the slow request's response).
    """
    client.get("/health")  # warm-up, so the timed request measures waiting only
    outcome: Dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["response"] = slow_request()
        except BaseException as e:  # re-raised in the test thread below
            outcome["error"] = e

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    assert started.wait(15), "the slow call never started"

    begin = time.perf_counter()
    health = client.get("/health")
    elapsed = time.perf_counter() - begin

    worker.join(60)
    assert not worker.is_alive(), "the slow request never finished"
    if "error" in outcome:
        raise outcome["error"]
    assert health.status_code == 200
    return elapsed, outcome["response"]


@pytest.fixture
def services(client: Any) -> Any:
    return client.app.state.services


# --- /health stays responsive -------------------------------------------------------------------

def test_health_answers_while_an_upload_is_embedding(
    client: Any, account: Account, services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    embedder = services.indexing_service.embedding_service
    original = embedder.embed_texts

    def slow_embed(texts: List[str]) -> Any:
        started.set()
        time.sleep(SLOW_SECONDS)  # stands in for Day 16's per-minute pacing
        return original(texts)

    monkeypatch.setattr(embedder, "embed_texts", slow_embed)

    elapsed, response = health_time_while(client, started, lambda: upload(client, account))

    assert response.status_code == 200, response.text
    assert response.json()["chunks_indexed"] > 0
    assert elapsed < HEALTH_BUDGET_SECONDS, f"/health took {elapsed:.2f} s during an upload"


def test_health_answers_while_a_chat_turn_is_retrieving(
    client: Any, account: Account, services: Any, gemini: FakeGemini, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload(client, account)
    started = threading.Event()
    embedder = services.query_embedding_service
    original = embedder.embed_texts

    def slow_query_embed(texts: List[str]) -> Any:
        if not started.is_set():
            started.set()
            time.sleep(SLOW_SECONDS)  # stands in for embeddings + Tavily before the stream starts
        return original(texts)

    monkeypatch.setattr(embedder, "embed_texts", slow_query_embed)

    elapsed, events = health_time_while(client, started, lambda: chat(client, account))

    assert_contract(events)
    assert elapsed < HEALTH_BUDGET_SECONDS, f"/health took {elapsed:.2f} s before a chat stream started"


def test_health_answers_while_a_chat_answer_is_streaming(
    client: Any, account: Account, services: Any, gemini: FakeGemini, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()

    def slow_stream(prompt: Dict[str, Any]) -> Iterator[str]:
        yield "Documents are "
        started.set()
        time.sleep(SLOW_SECONDS)  # a slow Gemini between two tokens
        yield "indexed."

    monkeypatch.setattr(services.llm_client, "stream_answer", slow_stream)

    elapsed, events = health_time_while(client, started, lambda: chat(client, account))

    assert assert_contract(events)["answer"] == "Documents are indexed."
    assert elapsed < HEALTH_BUDGET_SECONDS, f"/health took {elapsed:.2f} s while an answer streamed"


def test_health_answers_while_a_cached_answer_is_replayed(
    client: Any, account: Account, gemini: FakeGemini, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload(client, account)
    first = assert_contract(chat(client, account))
    started = threading.Event()
    original = ChatPipeline._close_turn

    def slow_close_turn(*args: Any, **kwargs: Any) -> int:
        started.set()
        time.sleep(SLOW_SECONDS)  # the replay's commit, on a slow database
        return original(*args, **kwargs)

    monkeypatch.setattr(ChatPipeline, "_close_turn", staticmethod(slow_close_turn))

    elapsed, events = health_time_while(
        client, started, lambda: chat(client, account, session_id=first["metadata"]["session_id"])
    )

    assert gemini.stream_calls == 1  # the second turn was the cached replay
    assert assert_contract(events)["answer"] == first["answer"]
    assert elapsed < HEALTH_BUDGET_SECONDS, f"/health took {elapsed:.2f} s during a cached replay"


# --- No DB connection held through slow external calls ------------------------------------------

def test_an_upload_holds_no_db_connection_while_embedding(
    client: Any, account: Account, services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    held: List[int] = []
    embedder = services.indexing_service.embedding_service
    original = embedder.embed_texts

    def recording_embed(texts: List[str]) -> Any:
        held.append(engine.pool.checkedout())
        return original(texts)

    monkeypatch.setattr(embedder, "embed_texts", recording_embed)

    response = upload(client, account)

    assert response.status_code == 200, response.text
    assert held, "the upload never embedded anything"
    assert held == [0] * len(held), f"connections checked out during embedding: {held}"


def test_a_chat_turn_holds_no_db_connection_while_tokens_stream(
    client: Any, account: Account, services: Any, gemini: FakeGemini, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload(client, account)
    held: List[int] = []

    def recording_stream(prompt: Dict[str, Any]) -> Iterator[str]:
        for token in ("Documents ", "are ", "indexed."):
            held.append(engine.pool.checkedout())
            yield token

    monkeypatch.setattr(services.llm_client, "stream_answer", recording_stream)

    assert_contract(chat(client, account))

    assert held == [0, 0, 0], f"connections checked out while tokens streamed: {held}"


def test_index_document_refuses_a_session_with_uncommitted_writes(
    client: Any, services: Any, gemini: FakeGemini
) -> None:
    # It ends the caller's transaction before embedding; committing someone else's writes there
    # would be a surprise, so it refuses them, unflushed or flushed.
    with SessionLocal() as db:
        user = User(email=f"pending-{uuid.uuid4().hex[:12]}@example.com")
        db.add(user)
        db.flush()
        document = Document(
            user_id=user.id, file_name="samples.pdf", file_path="unused", file_hash="0" * 64,
            version=1, is_active=True,
        )
        db.add(document)  # unflushed: in db.new
        with pytest.raises(PendingWrites):
            services.indexing_service.index_document(
                db, file_path=str(SAMPLE_PDF), user_id=user.id, document_id=0, document_version=1,
                file_name="samples.pdf",
            )
        db.flush()  # flushed: only Postgres knows about the write
        with pytest.raises(PendingWrites):
            services.indexing_service.index_document(
                db, file_path=str(SAMPLE_PDF), user_id=user.id, document_id=document.id,
                document_version=1, file_name="samples.pdf",
            )
        db.rollback()
    assert gemini.embed_calls == 0


def test_a_document_deleted_while_embedding_is_refused_and_leaves_nothing_behind(
    client: Any, account: Account, services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = client.get("/me", headers=account.headers).json()["id"]
    embedder = services.indexing_service.embedding_service
    original = embedder.embed_texts
    deleted_keys: List[str] = []

    def embed_while_the_user_deletes(texts: List[str]) -> Any:
        # Requests run in parallel now: the user deletes the file from another tab mid-upload.
        with SessionLocal() as db:
            ((document, _project),) = documents_repo.list_active_with_project(db, owner_id)
            deleted_keys.append(document.file_path)
            document_service.delete_document(db, owner_id, document.id, services.file_storage)
        return original(texts)

    monkeypatch.setattr(embedder, "embed_texts", embed_while_the_user_deletes)

    response = upload(client, account)

    assert response.status_code == 409, response.text
    assert "deleted while it was being indexed" in response.json()["detail"]
    assert client.get("/documents", headers=account.headers).json() == []
    with SessionLocal() as db:
        assert chunks_repo.count_for_user(db, owner_id) == 0
    assert deleted_keys and not services.file_storage.exists(deleted_keys[0])


# --- Regression guard ---------------------------------------------------------------------------

def test_routes_are_plain_def_unless_allowlisted(app: Any) -> None:
    offenders = sorted(
        f"{','.join(sorted(route.methods))} {route.path} ({route.endpoint.__name__})"
        for route in app.routes
        if isinstance(route, APIRoute)
        and inspect.iscoroutinefunction(route.endpoint)
        and route.path not in ASYNC_ROUTE_ALLOWLIST
    )
    assert not offenders, (
        "These routes are `async def`, so their sync DB / Gemini / network calls block the event loop "
        "(one uvicorn worker: /health times out and Render restarts the instance mid-stream). Make them "
        "plain `def` (FastAPI runs those in its threadpool), or, if a route awaits and never blocks, add "
        f"it to ASYNC_ROUTE_ALLOWLIST: {offenders}"
    )
