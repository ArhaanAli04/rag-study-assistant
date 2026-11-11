#session management+ CRUD + auto create
from sqlalchemy.orm import Session as DBSession
from app.db.models import Session as ChatSession, Message
from app.db.repositories import messages as messages_repo
from typing import Optional
def create_session(db: DBSession, user_id: int, title: str | None = None) -> ChatSession:
    s = ChatSession(user_id=user_id, title=title)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s

def get_or_create_session(
    db: DBSession,
    user_id: int,
    session_id: Optional[int],
    first_query: Optional[str],
) -> ChatSession:
    if session_id is not None:
        s = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .first()
        )
        if s:
            return s

    title = (first_query[:60] + "...") if first_query else "New session"
    return create_session(db, user_id, title)

def add_message(db: DBSession, session_id: int, user_id: int, role: str, content: str, sources: str | None = None) -> int:
    """Store one turn and commit it at once, so it survives a failure later in the request.

    The id is the SSE message_id frame's payload. Day 13: the raw INSERT + cursor.lastrowid this
    replaces returned no row id on Postgres; the repository reads it back on every backend.
    """
    message = messages_repo.add(db, session_id=session_id, user_id=user_id, role=role, content=content, sources=sources)
    db.commit()
    return message.id


def get_recent_messages(
    db: DBSession,
    session_id: int,
    limit: int = 20,
):
    """
    Return the most recent `limit` messages for the session in chronological order
    (oldest first), ready to pass directly to llm_client.build_prompt as prior turns.
    """
    rows = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))  # convert to chronological order here