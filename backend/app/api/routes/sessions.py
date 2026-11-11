from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.db.repositories import messages as messages_repo, sessions as sessions_repo

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("")
async def get_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Get all chat sessions ordered by most recent message"""
    return [
        {
            "id": session.id,
            "title": session.title,
            "topic": session.topic or "General",
            "created_at": session.created_at.isoformat() + 'Z' if session.created_at else None,
            "last_message_time": last_msg_time.isoformat() + 'Z' if last_msg_time else None,
        }
        for session, last_msg_time in sessions_repo.list_with_last_message(db, current_user.id)
    ]


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Get all messages in a session."""
    if sessions_repo.get_owned(db, session_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources":  m.sources.split(',') if m.sources else [],
            "created_at": m.timestamp.isoformat(),  # the column is `timestamp`; the API calls it created_at
        }
        for m in messages_repo.list_for_session(db, session_id)
    ]


@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete a chat session"""
    session = sessions_repo.get_owned(db, session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    sessions_repo.delete_with_messages(db, session)
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

    session = sessions_repo.get_owned(db, session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
