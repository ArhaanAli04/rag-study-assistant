from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import Message, Session as ChatSession, User

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("")
async def get_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Get all chat sessions ordered by most recent message"""

    # Subquery to get the latest message timestamp for each session
    latest_message = (
        db.query(
            Message.session_id,
            func.max(Message.timestamp).label('last_message_time')
        )
        .group_by(Message.session_id)
        .subquery()
    )

    # Query sessions with their latest message time
    sessions_with_time = (
        db.query(
            ChatSession,
            latest_message.c.last_message_time
        )
        .outerjoin(latest_message, ChatSession.id == latest_message.c.session_id)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(desc(latest_message.c.last_message_time).nulls_last())
        .all()
    )

    # Build response
    result = []
    for session, last_msg_time in sessions_with_time:
        result.append({
            "id": session.id,
            "title": session.title,
            "topic": session.topic or "General",
            "created_at": session.created_at.isoformat() + 'Z' if session.created_at else None,
            "last_message_time": last_msg_time.isoformat() + 'Z' if last_msg_time else None,
        })

    return result


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Get all messages in a session."""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.timestamp.asc())
        .all()
    )

    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources":  m.sources.split(',') if m.sources else [],
            "created_at": m.timestamp.isoformat(),  # the column is `timestamp`; the API calls it created_at
        }
        for m in messages
    ]


@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete a chat session"""

    # Find the session
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Delete associated messages first (if not cascade deleted)
    db.query(Message).filter(Message.session_id == session_id).delete()

    # Delete the session
    db.delete(session)
    db.commit()

    return {"message": "Session deleted successfully"}


@router.patch("/{session_id}/rename")
async def rename_session(
    session_id: int,
    new_title: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Rename a chat session"""

    # Validate title
    if not new_title or len(new_title.strip()) == 0:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    if len(new_title) > 100:
        raise HTTPException(status_code=400, detail="Title too long (max 100 characters)")

    # Find the session
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Update title
    session.title = new_title.strip()
    db.commit()
    db.refresh(session)

    return {
        "message": "Session renamed successfully",
        "session": {
            "id": session.id,
            "title": session.title,
            "topic": session.topic or "General",
            "created_at": session.created_at.isoformat() + 'Z' if session.created_at else None,
        }
    }
