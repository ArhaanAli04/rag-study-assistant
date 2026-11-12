"""T2 (Day 13): the repositories, above all their ownership scoping.

Runs on two databases:
- default: a temporary SQLite file migrated through Alembic, like the rest of the suite.
- TEST_DATABASE_URL set (the suite's Postgres _test database since Day 14, which conftest has
  already migrated to head): the same tests on Postgres, which compares types strictly. A filter
  like `Document.user_id == str(user.id)` passes on SQLite and fails there, so CI catches it
  instead of production.

Each test runs inside one transaction that is rolled back afterwards. Repositories only flush,
never commit, so nothing persists between tests on either backend.
"""
import datetime
import os
from pathlib import Path
from typing import Iterator, Tuple

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.db.migrations import alembic_config
from app.db.models import Document, Message, Session as ChatSession, User
from app.db.repositories import (
    documents as documents_repo,
    failed_queries as failed_queries_repo,
    messages as messages_repo,
    sessions as sessions_repo,
    users as users_repo,
)
from app.db.session import build_engine

POSTGRES_URL = os.environ.get("TEST_DATABASE_URL")
T0 = datetime.datetime(2026, 11, 11, 12, 0, 0)


@pytest.fixture(scope="module")
def engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    if POSTGRES_URL:
        engine = build_engine(POSTGRES_URL)
    else:
        path: Path = tmp_path_factory.mktemp("repositories") / "repositories.db"
        engine = create_engine(f"sqlite:///{path.as_posix()}")
        config = alembic_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def two_users(db: Session) -> Tuple[User, User]:
    alice = users_repo.create_password_user(db, "alice@example.com", "hash-a")
    bob = users_repo.create_password_user(db, "bob@example.com", "hash-b")
    return alice, bob


def test_backend_under_test(engine: Engine) -> None:
    # Makes the CI log say which database this module actually ran against.
    assert engine.dialect.name == ("postgresql" if POSTGRES_URL else "sqlite")


# --- users ----------------------------------------------------------------------------------------

def test_create_password_user_assigns_an_id_and_is_found_by_email(db: Session) -> None:
    user = users_repo.create_password_user(db, "carol@example.com", "hash-c")

    assert isinstance(user.id, int)
    assert users_repo.get_by_email(db, "carol@example.com") is user
    assert users_repo.get_by_email(db, "nobody@example.com") is None


def test_create_oauth_user_has_no_password(db: Session) -> None:
    user = users_repo.create_oauth_user(db, "dana@example.com", "Dana", "https://img/d.png", provider="google")

    assert (user.hashed_password, user.oauth_provider, user.name, user.username) == (None, "google", "Dana", "Dana")


# --- sessions -------------------------------------------------------------------------------------

def _session(db: Session, user: User, title: str) -> ChatSession:
    session = ChatSession(user_id=user.id, title=title)
    db.add(session)
    db.flush()
    return session


def _message(db: Session, session: ChatSession, user: User, role: str, at: datetime.datetime) -> Message:
    message = messages_repo.add(db, session_id=session.id, user_id=user.id, role=role, content=f"{role} at {at}", sources=None)
    message.timestamp = at
    db.flush()
    return message


def test_sessions_are_listed_for_their_owner_only_most_recent_first(db: Session, two_users: Tuple[User, User]) -> None:
    alice, bob = two_users
    older, newer, empty = _session(db, alice, "older"), _session(db, alice, "newer"), _session(db, alice, "empty")
    _message(db, older, alice, "user", T0)
    _message(db, newer, alice, "user", T0 + datetime.timedelta(hours=1))
    _session(db, bob, "bob's")

    listed = sessions_repo.list_with_last_message(db, alice.id)

    assert [(s.title, last) for s, last in listed] == [
        ("newer", T0 + datetime.timedelta(hours=1)),
        ("older", T0),
        ("empty", None),
    ]


def test_a_session_is_not_found_for_another_user(db: Session, two_users: Tuple[User, User]) -> None:
    alice, bob = two_users
    session = _session(db, alice, "alice's")

    assert sessions_repo.get_owned(db, session.id, alice.id) is session
    assert sessions_repo.get_owned(db, session.id, bob.id) is None


def test_deleting_a_session_deletes_its_messages(db: Session, two_users: Tuple[User, User]) -> None:
    alice, _ = two_users
    session = _session(db, alice, "to delete")
    _message(db, session, alice, "user", T0)
    _message(db, session, alice, "assistant", T0)

    sessions_repo.delete_with_messages(db, session)
    db.flush()

    assert db.query(Message).filter(Message.session_id == session.id).count() == 0
    assert sessions_repo.get_owned(db, session.id, alice.id) is None


def test_deleting_a_session_keeps_its_failed_queries_detached(db: Session, two_users: Tuple[User, User]) -> None:
    # Postgres enforces failed_queries.session_id's foreign key; SQLite let the session go and left
    # the row pointing at nothing, so this delete returned 500 only on Postgres (found Day 14).
    alice, _ = two_users
    session = _session(db, alice, "low confidence")
    failed = failed_queries_repo.add(db, user_id=alice.id, session_id=session.id, query="q", reason="low_confidence", confidence=10)
    db.flush()

    sessions_repo.delete_with_messages(db, session)
    db.flush()
    db.expire(failed)

    assert failed.session_id is None
    assert [f.query for f in failed_queries_repo.list_recent(db, alice.id, limit=10)] == ["q"]


# --- documents ------------------------------------------------------------------------------------

def _document(db: Session, user: User, name: str, active: bool = True) -> Document:
    document = Document(user_id=user.id, file_name=name, file_path=f"uploads/{user.id}/{name}", file_hash=name, is_active=active)
    db.add(document)
    db.flush()
    return document


def test_documents_are_scoped_to_their_owner(db: Session, two_users: Tuple[User, User]) -> None:
    alice, bob = two_users
    first, second = _document(db, alice, "a1.pdf"), _document(db, alice, "a2.pdf")
    _document(db, alice, "old.pdf", active=False)
    bobs = _document(db, bob, "b1.pdf")

    assert [d.file_name for d in documents_repo.list_active(db, alice.id)] == ["a2.pdf", "a1.pdf"]
    assert documents_repo.count_active(db, alice.id) == 2
    assert documents_repo.get_owned(db, first.id, alice.id) is first
    assert documents_repo.get_owned(db, bobs.id, alice.id) is None
    assert second.id > first.id


# --- messages and feedback ------------------------------------------------------------------------

def test_added_message_has_an_integer_id(db: Session, two_users: Tuple[User, User]) -> None:
    # The SSE message_id frame carries this id; the raw INSERT + lastrowid it replaced gave none
    # on Postgres.
    alice, _ = two_users
    session = _session(db, alice, "chat")

    message = messages_repo.add(db, session_id=session.id, user_id=alice.id, role="assistant", content="hi", sources=None)

    assert isinstance(message.id, int)
    assert message.sources == ""


def test_a_message_is_not_found_for_another_user(db: Session, two_users: Tuple[User, User]) -> None:
    alice, bob = two_users
    message = _message(db, _session(db, alice, "chat"), alice, "assistant", T0)

    assert messages_repo.get_owned(db, message.id, alice.id) is message
    assert messages_repo.get_owned(db, message.id, bob.id) is None


def test_feedback_and_the_question_behind_an_answer(db: Session, two_users: Tuple[User, User]) -> None:
    alice, _ = two_users
    session = _session(db, alice, "chat")
    _message(db, session, alice, "user", T0)
    question = _message(db, session, alice, "user", T0 + datetime.timedelta(minutes=1))
    answer = _message(db, session, alice, "assistant", T0 + datetime.timedelta(minutes=2))

    messages_repo.set_feedback(answer, "down", "wrong")
    db.flush()
    db.expire(answer)

    assert (answer.feedback, answer.feedback_comment) == ("down", "wrong")
    assert messages_repo.previous_user_message(db, answer) is question
    assert [m.role for m in messages_repo.list_for_session(db, session.id)] == ["user", "user", "assistant"]


# --- failed queries -------------------------------------------------------------------------------

def test_failed_queries_are_scoped_newest_first_and_limited(db: Session, two_users: Tuple[User, User]) -> None:
    alice, bob = two_users
    for minute in range(3):
        failed = failed_queries_repo.add(db, user_id=alice.id, session_id=None, query=f"q{minute}", reason="low_confidence", confidence=10)
        failed.timestamp = T0 + datetime.timedelta(minutes=minute)
    failed_queries_repo.add(db, user_id=bob.id, session_id=None, query="bob's", reason="negative_feedback", feedback="down")
    db.flush()

    assert [f.query for f in failed_queries_repo.list_recent(db, alice.id, limit=2)] == ["q2", "q1"]
    assert [f.query for f in failed_queries_repo.list_recent(db, bob.id, limit=50)] == ["bob's"]
