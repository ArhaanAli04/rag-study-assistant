import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.database import FailedQuery, Message, User
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
    # Verify message belongs to user
    msg = db.query(Message).filter(
        Message.id == message_id,
        Message.user_id == str(current_user.id)
    ).first()

    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Update feedback using raw SQL
    sql = text("""
        UPDATE messages
        SET feedback = :feedback, feedback_comment = :comment
        WHERE id = :message_id
    """)

    db.execute(sql, {
        'feedback': body.feedback,
        'comment': body.comment or "",
        'message_id': message_id
    })

    # A thumbs down is also logged as a failed query, against the question that led to the answer.
    if body.feedback == 'down':
        user_msg = db.query(Message).filter(
            Message.session_id == msg.session_id,
            Message.role == 'user',
            Message.id < msg.id
        ).order_by(Message.id.desc()).first()

        if user_msg:
            failed_query = FailedQuery(
                user_id=str(current_user.id),
                session_id=msg.session_id,
                query=user_msg.content,
                confidence=None,  # Can be populated if you track confidence
                feedback='down',
                reason='negative_feedback',
                comment=body.comment or "",
                timestamp=datetime.datetime.utcnow()
            )
            db.add(failed_query)

    db.commit()

    return {"status": "ok", "message_id": message_id}


@router.get("/analytics/failed-queries")
async def get_failed_queries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get recent failed queries for analysis"""
    failed_queries = db.query(FailedQuery).filter(
        FailedQuery.user_id == str(current_user.id)
    ).order_by(FailedQuery.timestamp.desc()).limit(limit).all()

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
        for fq in failed_queries
    ]
