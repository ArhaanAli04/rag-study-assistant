from sqlalchemy.orm import Session

from app.db.models import Message


def add(db: Session, session_id: int, user_id: int, role: str, content: str, sources: str | None) -> Message:
    message = Message(session_id=session_id, user_id=user_id, role=role, content=content, sources=sources or "")
    db.add(message)
    # flush, not lastrowid: on Postgres a cursor's lastrowid is not the new row's id, while the
    # ORM reads it back (RETURNING) on every backend. The SSE message_id frame depends on it.
    db.flush()
    return message


def get_owned(db: Session, message_id: int, user_id: int) -> Message | None:
    return db.query(Message).filter(Message.id == message_id, Message.user_id == user_id).first()


def list_for_session(db: Session, session_id: int) -> list[Message]:
    return db.query(Message).filter(Message.session_id == session_id).order_by(Message.timestamp.asc()).all()


def set_feedback(message: Message, feedback: str, comment: str) -> None:
    message.feedback = feedback
    message.feedback_comment = comment


def previous_user_message(db: Session, message: Message) -> Message | None:
    """The user's question that an assistant message answered: the latest earlier user turn."""
    return (
        db.query(Message)
        .filter(Message.session_id == message.session_id, Message.role == "user", Message.id < message.id)
        .order_by(Message.id.desc())
        .first()
    )
