"""projects: a user's projects and their counts (Day 18). Plain functions; the caller commits."""
import datetime
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Document, Message, Project, Session as ChatSession


@dataclass(frozen=True)
class ProjectSummary:
    project: Project
    document_count: int
    chat_count: int
    # The newest message in any of its chats; None while it has none.
    last_activity: datetime.datetime | None


def get_owned(db: Session, project_id: int, user_id: int) -> Project | None:
    """The user's project, or None: another user's id looks exactly like a missing one (404, not 403)."""
    return db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))


def name_taken(db: Session, user_id: int, name: str, exclude_project_id: int | None = None) -> bool:
    """Whether another of the user's projects (archived ones too) already has this name."""
    query = select(Project.id).where(Project.user_id == user_id, Project.name == name)
    if exclude_project_id is not None:
        query = query.where(Project.id != exclude_project_id)
    return db.scalar(query.limit(1)) is not None


def add(db: Session, user_id: int, name: str, description: str | None, instructions: str | None) -> Project:
    project = Project(user_id=user_id, name=name, description=description, instructions=instructions)
    db.add(project)
    db.flush()
    return project


def list_with_counts(db: Session, user_id: int) -> list[ProjectSummary]:
    """Every project of the user with its active-document count, chat count and last activity, in one
    statement (CO6: each round trip crosses regions). Most recently created first."""
    documents = (
        select(Document.project_id, func.count().label("n"))
        .where(Document.user_id == user_id, Document.is_active.is_(True), Document.project_id.is_not(None))
        .group_by(Document.project_id)
        .subquery()
    )
    chats = (
        select(
            ChatSession.project_id,
            func.count(func.distinct(ChatSession.id)).label("n"),
            func.max(Message.timestamp).label("last_message"),
        )
        .outerjoin(Message, Message.session_id == ChatSession.id)
        .where(ChatSession.user_id == user_id, ChatSession.project_id.is_not(None))
        .group_by(ChatSession.project_id)
        .subquery()
    )
    rows = db.execute(
        select(Project, documents.c.n, chats.c.n, chats.c.last_message)
        .outerjoin(documents, documents.c.project_id == Project.id)
        .outerjoin(chats, chats.c.project_id == Project.id)
        .where(Project.user_id == user_id)
        .order_by(Project.id.desc())
    )
    return [
        ProjectSummary(project=project, document_count=n_docs or 0, chat_count=n_chats or 0, last_activity=last)
        for project, n_docs, n_chats, last in rows
    ]
