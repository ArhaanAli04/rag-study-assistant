import datetime

from sqlalchemy.orm import Session

from app.db.models import FailedQuery


def add(
    db: Session,
    user_id: int,
    session_id: int | None,
    query: str,
    reason: str,
    confidence: int | None = None,
    feedback: str | None = None,
    comment: str = "",
) -> FailedQuery:
    failed_query = FailedQuery(
        user_id=user_id,
        session_id=session_id,
        query=query,
        confidence=confidence,
        feedback=feedback,
        reason=reason,
        comment=comment,
        timestamp=datetime.datetime.utcnow(),
    )
    db.add(failed_query)
    return failed_query


def list_recent(db: Session, user_id: int, limit: int) -> list[FailedQuery]:
    return (
        db.query(FailedQuery)
        .filter(FailedQuery.user_id == user_id)
        .order_by(FailedQuery.timestamp.desc())
        .limit(limit)
        .all()
    )
