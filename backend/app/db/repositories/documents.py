from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models import Document


def get_owned(db: Session, document_id: int, user_id: int) -> Document | None:
    return db.query(Document).filter(Document.id == document_id, Document.user_id == user_id).first()


def list_active(db: Session, user_id: int) -> list[Document]:
    """Newest first. Ordered by id, which grows with every upload."""
    return (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.is_active.is_(True))
        .order_by(desc(Document.id))
        .all()
    )


def count_active(db: Session, user_id: int) -> int:
    return db.query(Document).filter(Document.user_id == user_id, Document.is_active.is_(True)).count()


def latest_version(db: Session, user_id: int, file_name: str) -> Document | None:
    return (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.file_name == file_name)
        .order_by(desc(Document.version))
        .first()
    )


def list_versions(db: Session, user_id: int, file_name: str) -> list[Document]:
    """Every version of one of the user's file names, newest first."""
    return (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.file_name == file_name)
        .order_by(desc(Document.version))
        .all()
    )
