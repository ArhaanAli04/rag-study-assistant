"""Projects: ownership checks, create / update / delete, and moving documents and chats (Day 18).

Every function takes the user's id and resolves the project through it, so another user's project
id behaves exactly like a missing one (ProjectNotFound → 404). Nothing here raises HTTP errors; the
routes map these exceptions to status codes.
"""
import datetime
import logging
from dataclasses import dataclass
from typing import Literal, Optional

from sqlalchemy.orm import Session

from app.db.models import Document, Project, User
from app.db.repositories import documents as documents_repo
from app.db.repositories import projects as projects_repo
from app.db.repositories import sessions as sessions_repo
from app.db.repositories import users as users_repo
from app.ingestion.upload_storage import FileStorage
from app.services.document_service import delete_files_quietly

logger = logging.getLogger("rag_assistant.projects")

DocumentsOnDelete = Literal["delete", "unassign"]


class ProjectNotFound(Exception):
    """No such project for this user (or it is another user's)."""


class ProjectArchived(Exception):
    """An archived project takes no new uploads or chats."""


class ProjectNameTaken(Exception):
    """The user already has a project with this name."""


class DocumentNotFound(Exception):
    """No such document for this user."""


class SessionNotFound(Exception):
    """No such chat session for this user."""


class FileNameClash(Exception):
    """Moving would put two active documents of one name in the same project (or in no project)."""

    def __init__(self, file_names: list[str]) -> None:
        super().__init__(", ".join(file_names))
        self.file_names = file_names


def require_owned(db: Session, user_id: int, project_id: int) -> Project:
    project = projects_repo.get_owned(db, project_id, user_id)
    if project is None:
        raise ProjectNotFound(project_id)
    return project


def require_target(db: Session, user_id: int, project_id: int | None) -> Optional[Project]:
    """A project new content may go into: the user's own and not archived. None (no project) passes.

    Ownership is checked before the archive flag, so another user's archived project is a 404, not a
    409 that would confirm it exists."""
    if project_id is None:
        return None
    project = require_owned(db, user_id, project_id)
    if project.archived_at is not None:
        raise ProjectArchived(project_id)
    return project


def create_project(
    db: Session, user_id: int, name: str, description: str | None, instructions: str | None
) -> Project:
    if projects_repo.name_taken(db, user_id, name):
        raise ProjectNameTaken(name)
    project = projects_repo.add(db, user_id, name, description, instructions)
    db.commit()
    db.refresh(project)
    return project


def update_project(db: Session, user_id: int, project_id: int, changes: dict[str, object]) -> Project:
    """Apply the fields the client sent (``changes``); ``archived`` sets or clears archived_at."""
    project = require_owned(db, user_id, project_id)
    name = changes.get("name")
    if isinstance(name, str) and name != project.name:
        if projects_repo.name_taken(db, user_id, name, exclude_project_id=project.id):
            raise ProjectNameTaken(name)
        project.name = name
    for field in ("description", "instructions"):
        if field in changes:
            setattr(project, field, changes[field])
    archived = changes.get("archived")
    if archived is True and project.archived_at is None:
        project.archived_at = datetime.datetime.utcnow()
    elif archived is False:
        project.archived_at = None
    db.commit()
    db.refresh(project)
    return project


@dataclass(frozen=True)
class DeletedProject:
    documents_deleted: int
    documents_unassigned: int
    chats_unassigned: int
    files_removed: int
    doc_version: int


def delete_project(
    db: Session, user_id: int, project_id: int, documents: DocumentsOnDelete, storage: FileStorage
) -> DeletedProject:
    """Delete a project: its documents are deleted or moved to no project, as the user chose; its
    chats always move to no project (Decision 4A). One commit with the doc_version bump, then the
    stored files of deleted documents.

    Unassigning is refused (FileNameClash) when a file name would then be active twice in no project:
    versioning picks one document per (user, project, name), so the other would be unreachable."""
    project = require_owned(db, user_id, project_id)
    # Every version, active or not: none may outlive its project, or stay behind in it.
    rows = documents_repo.list_in_project(db, user_id, project.id)
    active = [d for d in rows if d.is_active]
    keys: list[str] = []

    if documents == "unassign":
        clashes = _clashes(db, user_id, None, active)
        if clashes:
            raise FileNameClash(clashes)
        documents_repo.set_project(db, user_id, [d.id for d in rows], None)
    else:
        keys = [d.file_path for d in rows]
        for row in rows:
            db.delete(row)  # its chunks go by ON DELETE CASCADE (I5)

    chats = sessions_repo.unassign_project(db, user_id, project.id)
    db.delete(project)
    # Both choices change what some scope searches, so every cache keyed on doc_version moves on.
    doc_version = users_repo.increment_doc_version(db, user_id)
    db.commit()

    files_removed = delete_files_quietly(storage, user_id, keys)
    logger.info(
        "Deleted project %s of user %s: %s documents %s (%s rows), %s chats unassigned",
        project_id, user_id, len(active), documents, len(rows), chats,
    )
    return DeletedProject(
        documents_deleted=len(active) if documents == "delete" else 0,
        documents_unassigned=len(active) if documents == "unassign" else 0,
        chats_unassigned=chats,
        files_removed=files_removed,
        doc_version=doc_version,
    )


def move_document(db: Session, user_id: int, document_id: int, project_id: int | None) -> int:
    """Move a document, with every version of its file name, to a project (or to none); returns the
    new doc_version. The target must be the user's and not archived; an active document of the same
    name already there is a FileNameClash (409)."""
    document = documents_repo.get_owned(db, document_id, user_id)
    if document is None:
        raise DocumentNotFound(document_id)
    require_target(db, user_id, project_id)
    if document.project_id == project_id:
        # Already there: nothing changes scope, so no doc_version bump.
        return db.get(User, user_id).doc_version
    versions = documents_repo.versions_of(db, document)
    active = [v for v in versions if v.is_active]
    clashes = _clashes(db, user_id, project_id, active)
    if clashes:
        raise FileNameClash(clashes)
    documents_repo.set_project(db, user_id, [v.id for v in versions], project_id)
    # The document left one scope and joined another: caches keyed on doc_version must not replay.
    doc_version = users_repo.increment_doc_version(db, user_id)
    db.commit()
    return doc_version


def move_session(db: Session, user_id: int, session_id: int, project_id: int | None) -> None:
    """Move a chat to a project (or to none). No doc_version bump: no document changed scope, and the
    chat's next turn searches its new scope."""
    session = sessions_repo.get_owned(db, session_id, user_id)
    if session is None:
        raise SessionNotFound(session_id)
    require_target(db, user_id, project_id)
    sessions_repo.set_project(db, session_id, user_id, project_id)
    db.commit()


def _clashes(db: Session, user_id: int, project_id: int | None, active: list[Document]) -> list[str]:
    """Names among ``active`` that already have an active document in the target project."""
    return sorted({
        d.file_name for d in active
        if (other := documents_repo.active_name_in_project(db, user_id, project_id, d.file_name)) is not None
        and other.id != d.id
    })
