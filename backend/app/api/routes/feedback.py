from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.db.repositories import failed_queries as failed_queries_repo, messages as messages_repo
from app.schemas.feedback import FeedbackRequest

router = APIRouter(tags=["Feedback"])


@router.post("/messages/{message_id}/feedback")
async def submit_feedback(
    message_id: int,
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Submit thumbs up/down feedback for a message"""
    msg = messages_repo.get_owned(db, message_id, current_user.id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    messages_repo.set_feedback(msg, body.feedback, body.comment or "")

    # A thumbs down is also logged as a failed query, against the question that led to the answer.
    if body.feedback == 'down':
        user_msg = messages_repo.previous_user_message(db, msg)
        if user_msg:
            failed_queries_repo.add(
                db,
                user_id=current_user.id,
                session_id=msg.session_id,
                query=user_msg.content,
                reason='negative_feedback',
                feedback='down',
                comment=body.comment or "",
            )

    db.commit()

    return {"status": "ok", "message_id": message_id}


@router.get("/analytics/failed-queries")
async def get_failed_queries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get recent failed queries for analysis"""
    return [
        {
            "id": fq.id,
            "query": fq.query,
            "confidence": fq.confidence,
            "reason": fq.reason,
            "comment": fq.comment,
            "timestamp": fq.timestamp.isoformat() if fq.timestamp else None,
            "session_id": fq.session_id
        }
        for fq in failed_queries_repo.list_recent(db, current_user.id, limit)
    ]
