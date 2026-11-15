"""Chat sessions and their messages, for the chat pipeline (its only caller).

Nothing here commits (CO6, Day 16): every database round trip crosses Render → Supabase (~63 ms), so
the pipeline groups a step's writes into one transaction and commits once. Writes flush, which sends
the INSERT and reads the new id back (RETURNING) without ending the transaction.
"""
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from app.db.models import Message, Session as ChatSession
from app.db.repositories import messages as messages_repo

# Sessions start with this topic; the pipeline tags them while they still carry it.
DEFAULT_TOPIC = "General"


def get_or_create_session(
    db: DBSession,
    user_id: int,
    session_id: Optional[int],
    first_query: Optional[str],
) -> Tuple[ChatSession, bool]:
    """(the user's session `session_id`, False), or (a new one, True). The frontend sends 0 for a new
    chat, so 0 / None skip the lookup; an id that isn't this user's also gets a new session."""
    if session_id:
        existing = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .first()
        )
        if existing:
            return existing, False

    title = (first_query[:60] + "...") if first_query else "New session"
    created = ChatSession(user_id=user_id, title=title, topic=DEFAULT_TOPIC)
    db.add(created)
    db.flush()
    return created, True


def add_message(db: DBSession, session_id: int, user_id: int, role: str, content: str, sources: str | None = None) -> int:
    """Store one turn (flushed, not committed: the caller commits) and return its id.

    The id is the SSE message_id frame's payload. Day 13: the raw INSERT + cursor.lastrowid this
    replaced returned no row id on Postgres; the repository reads it back with RETURNING.
    """
    message = messages_repo.add(db, session_id=session_id, user_id=user_id, role=role, content=content, sources=sources)
    return message.id


def get_recent_messages(
    db: DBSession,
    session_id: int,
    limit: int = 20,
) -> List[Message]:
    """The most recent `limit` messages of the session, oldest first, ready to pass to
    llm_client.build_prompt as prior turns."""
    rows = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))
