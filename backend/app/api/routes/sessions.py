from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.routes.projects import ARCHIVED_PROJECT, PROJECT_NOT_FOUND
from app.db.models import User
from app.db.repositories import messages as messages_repo, sessions as sessions_repo
from app.schemas.projects import MoveToProject
from app.services import project_service
from app.services.project_service import ProjectArchived, ProjectNotFound, SessionNotFound

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("")
def get_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Get all chat sessions ordered by most recent message, each with its project (or none)."""
    return [
        {
            "id": session.id,
            "title": session.title,
            "topic": session.topic or "General",
            "created_at": session.created_at.isoformat() + 'Z' if session.created_at else None,
            "last_message_time": last_msg_time.isoformat() + 'Z' if last_msg_time else None,
            "project_id": session.project_id,
            "project_name": project_name,
        }
        for session, last_msg_time, project_name in sessions_repo.list_with_last_message(db, current_user.id)
    ]


@router.patch("/{session_id}/project")
def move_session(
    session_id: int,
    body: MoveToProject,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Move a chat to one of the user's projects (or to no project); its next turn searches there."""
    try:
        project_service.move_session(db, current_user.id, session_id, body.project_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="Session not found")
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND)
    except ProjectArchived:
        raise HTTPException(status_code=409, detail=ARCHIVED_PROJECT)
    return {"status": "moved", "session_id": session_id, "project_id": body.project_id}


@router.get("/{session_id}/messages")
def get_session_messages(
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
def delete_session(
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
def rename_session(
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
