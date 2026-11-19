from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from app.db.models import Document, Project

# A document's identity is (user_id, project_id, file_name) since Day 18 (Decision 2A): the same
# name in two projects is two documents. project_id may be NULL ("no project"), and NULL = NULL is
# not true in SQL, so the project comparisons use IS NOT DISTINCT FROM.


def get_owned(db: Session, document_id: int, user_id: int) -> Document | None:
    return db.query(Document).filter(Document.id == document_id, Document.user_id == user_id).first()


def lock_owned(db: Session, document_id: int, user_id: int) -> Document | None:
    """The document row, locked (FOR UPDATE) until the transaction ends; None if it is gone.

    Writing a document's chunks holds this lock, so a concurrent delete waits for that commit and
    then removes the chunks with the row, instead of racing the insert."""
    return (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user_id)
        .with_for_update()
        .first()
    )


def list_active_with_project(db: Session, user_id: int) -> list[tuple[Document, str | None]]:
    """Newest first (by id, which grows with every upload), each with its project's name (None: no
    project); one statement (CO6)."""
    rows = db.execute(
        select(Document, Project.name)
        .outerjoin(Project, Project.id == Document.project_id)
        .where(Document.user_id == user_id, Document.is_active.is_(True))
        .order_by(desc(Document.id))
    )
    return [(document, project_name) for document, project_name in rows]


def list_active_for_reindex(db: Session, user_id: int | None) -> list[Document]:
    """Active documents of one user, or of every user (None): the reindex script's work list only.
    Ordered by user, then id, so each user's documents are processed together."""
    query = db.query(Document).filter(Document.is_active.is_(True))
    if user_id is not None:
        query = query.filter(Document.user_id == user_id)
    return query.order_by(Document.user_id, Document.id).all()


def count_active(db: Session, user_id: int) -> int:
    return db.query(Document).filter(Document.user_id == user_id, Document.is_active.is_(True)).count()


def latest_version(db: Session, user_id: int, project_id: int | None, file_name: str) -> Document | None:
    return (
        db.query(Document)
        .filter(
            Document.user_id == user_id,
            Document.project_id.is_not_distinct_from(project_id),
            Document.file_name == file_name,
        )
        .order_by(desc(Document.version))
        .first()
    )


def list_versions(db: Session, user_id: int, project_id: int | None, file_name: str) -> list[Document]:
    """Every version of one file name of the user in one project (or in none), newest first."""
    return (
        db.query(Document)
        .filter(
            Document.user_id == user_id,
            Document.project_id.is_not_distinct_from(project_id),
            Document.file_name == file_name,
        )
        .order_by(desc(Document.version))
        .all()
    )


def versions_of(db: Session, document: Document) -> list[Document]:
    """Every version of the document's file name in its project, itself included, newest first."""
    return list_versions(db, document.user_id, document.project_id, document.file_name)


def active_name_in_project(
    db: Session, user_id: int, project_id: int | None, file_name: str
) -> Document | None:
    """The active document of that name in that project (or in none), if there is one."""
    return (
        db.query(Document)
        .filter(
            Document.user_id == user_id,
            Document.project_id.is_not_distinct_from(project_id),
            Document.file_name == file_name,
            Document.is_active.is_(True),
        )
        .first()
    )


def set_project(db: Session, user_id: int, document_ids: list[int], project_id: int | None) -> int:
    """Move these documents (every version of one file name) to a project or to none; one UPDATE."""
    if not document_ids:
        return 0
    result = db.execute(
        update(Document)
        .where(Document.user_id == user_id, Document.id.in_(document_ids))
        .values(project_id=project_id)
    )
    return result.rowcount


def list_in_project(db: Session, user_id: int, project_id: int) -> list[Document]:
    """Every row (all versions, active or not) of the user's documents in one project."""
    return (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.project_id == project_id)
        .order_by(desc(Document.id))
        .all()
    )
