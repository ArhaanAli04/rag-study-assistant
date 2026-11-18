import datetime

from sqlalchemy import desc, func, update
from sqlalchemy.orm import Session

from app.db.models import FailedQuery, Message, Project, Session as ChatSession


def list_with_last_message(
    db: Session, user_id: int, project_id: int | None = None
) -> list[tuple[ChatSession, datetime.datetime | None, str | None]]:
    """The user's sessions, most recent message first (sessions without messages last), each with
    its last message time and its project's name (None: no project). ``project_id`` keeps only that
    project's sessions; None lists every session."""
    latest_message = (
        db.query(Message.session_id, func.max(Message.timestamp).label("last_message_time"))
        .group_by(Message.session_id)
        .subquery()
    )
    query = (
        db.query(ChatSession, latest_message.c.last_message_time, Project.name)
        .outerjoin(latest_message, ChatSession.id == latest_message.c.session_id)
        .outerjoin(Project, Project.id == ChatSession.project_id)
        .filter(ChatSession.user_id == user_id)
    )
    if project_id is not None:
        query = query.filter(ChatSession.project_id == project_id)
    rows = query.order_by(desc(latest_message.c.last_message_time).nulls_last()).all()
    return [(session, last_message_time, project_name) for session, last_message_time, project_name in rows]


def set_project(db: Session, session_id: int, user_id: int, project_id: int | None) -> None:
    """Move one of the user's sessions to a project or to none; one UPDATE. The caller commits."""
    db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .values(project_id=project_id)
    )


def unassign_project(db: Session, user_id: int, project_id: int) -> int:
    """Move every session of a project to no project (Decision 4A); returns how many moved."""
    result = db.execute(
        update(ChatSession)
        .where(ChatSession.user_id == user_id, ChatSession.project_id == project_id)
        .values(project_id=None)
    )
    return result.rowcount


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
