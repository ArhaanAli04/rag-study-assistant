import datetime

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db.models import FailedQuery, Message, Session as ChatSession


def list_with_last_message(db: Session, user_id: int) -> list[tuple[ChatSession, datetime.datetime | None]]:
    """The user's sessions, most recent message first; sessions without messages last."""
    latest_message = (
        db.query(Message.session_id, func.max(Message.timestamp).label("last_message_time"))
        .group_by(Message.session_id)
        .subquery()
    )
    rows = (
        db.query(ChatSession, latest_message.c.last_message_time)
        .outerjoin(latest_message, ChatSession.id == latest_message.c.session_id)
        .filter(ChatSession.user_id == user_id)
        .order_by(desc(latest_message.c.last_message_time).nulls_last())
        .all()
    )
    return [(session, last_message_time) for session, last_message_time in rows]


def get_owned(db: Session, session_id: int, user_id: int) -> ChatSession | None:
    return (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )


def set_topic(db: Session, session_id: int, user_id: int, topic: str) -> None:
    """One UPDATE by id: no row is loaded first (CO6, Day 16). The caller commits."""
    db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id).update(
        {ChatSession.topic: topic}, synchronize_session=False
    )


def delete_with_messages(db: Session, session: ChatSession) -> None:
    """Delete a session and its messages; failed queries logged in it are kept, detached.

    Postgres enforces failed_queries.session_id's foreign key (SQLite never did), so they are
    detached before the session goes. The schema-level ON DELETE SET NULL comes on Day 15.
    """
    # Bulk-delete the messages first: the ORM cascade would load every message just to delete it.
    db.query(Message).filter(Message.session_id == session.id).delete(synchronize_session=False)
    db.query(FailedQuery).filter(FailedQuery.session_id == session.id).update(
        {FailedQuery.session_id: None}, synchronize_session=False
    )
    db.delete(session)
