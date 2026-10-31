#session management+ CRUD + auto create
from sqlalchemy.orm import Session as DBSession
from db import Session as ChatSession, Message
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

def add_message(db: DBSession, session_id: int, user_id: int, role: str, content: str, sources: str | None = None):
    from datetime import datetime
    from sqlalchemy import text
    
    # Use raw SQL to bypass ORM caching issues
    sql = text("""
        INSERT INTO messages (user_id, session_id, role, content, sources, feedback, feedback_comment, timestamp)
        VALUES (:user_id, :session_id, :role, :content, :sources, :feedback, :feedback_comment, :timestamp)
    """)
    
    result = db.execute(sql, {
        'user_id': str(user_id),
        'session_id': session_id,
        'role': role,
        'content': content,
        'sources': sources or "",
        'feedback': None,
        'feedback_comment': None,
        'timestamp': datetime.utcnow()
    })
    db.commit()
    
    # Get the last inserted ID
    message_id = result.lastrowid
    # Return messagwe_id
    return message_id


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