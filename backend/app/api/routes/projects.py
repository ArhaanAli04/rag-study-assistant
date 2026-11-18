"""Projects API (Day 18): a project is a course, with its own files, instructions and chats.

Every route is a plain def (B14: FastAPI runs it in its threadpool) and resolves the project
through the current user: another user's project id is a 404, exactly like a missing one.
"""
import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_services
from app.db.models import Project, User
from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.repositories import projects as projects_repo
from app.db.repositories import sessions as sessions_repo
from app.schemas.projects import (
    DocumentsOnDelete,
    ProjectChatOut,
    ProjectCreate,
    ProjectDeletedOut,
    ProjectDetailOut,
    ProjectDocumentOut,
    ProjectOut,
    ProjectUpdate,
)
from app.services import project_service
from app.services.container import Services
from app.services.project_service import FileNameClash, ProjectArchived, ProjectNameTaken, ProjectNotFound

router = APIRouter(prefix="/projects", tags=["Projects"])

PROJECT_NOT_FOUND = "Project not found"
ARCHIVED_PROJECT = "This project is archived. Unarchive it to add files or start chats."


def require_project_target(db: Session, user_id: int, project_id: int | None) -> None:
    """For routes that put new content in a project (upload, a new chat): 404 for a project that
    isn't the user's, 409 for an archived one; None (no project) passes."""
    try:
        project_service.require_target(db, user_id, project_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND)
    except ProjectArchived:
        raise HTTPException(status_code=409, detail=ARCHIVED_PROJECT)


def name_taken_error(name: str) -> HTTPException:
    return HTTPException(status_code=409, detail=f"You already have a project named “{name}”.")


def file_name_clash_error(error: FileNameClash, where: str) -> HTTPException:
    names = ", ".join(error.file_names)
    return HTTPException(
        status_code=409,
        detail=f"{where} already has a file named {names}. Rename or delete one of them first.",
    )


def _summary_out(summary: projects_repo.ProjectSummary) -> ProjectOut:
    return _project_out(summary.project, summary.document_count, summary.chat_count, summary.last_activity)


def _project_out(
    project: Project, document_count: int, chat_count: int, last_activity: datetime.datetime | None
) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        instructions=project.instructions,
        created_at=project.created_at,
        archived=project.archived_at is not None,
        document_count=document_count,
        chat_count=chat_count,
        last_activity=last_activity,
    )


def _summary_of(db: Session, user_id: int, project_id: int) -> projects_repo.ProjectSummary:
    for summary in projects_repo.list_with_counts(db, user_id):
        if summary.project.id == project_id:
            return summary
    raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND)


@router.post("", status_code=201, response_model=ProjectOut)
def create_project(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    try:
        project = project_service.create_project(db, current_user.id, body.name, body.description, body.instructions)
    except ProjectNameTaken:
        raise name_taken_error(body.name)
    return _project_out(project, 0, 0, None)


@router.get("", response_model=List[ProjectOut])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ProjectOut]:
    """Every project of the user, archived ones too (the client hides them from pickers)."""
    return [_summary_out(s) for s in projects_repo.list_with_counts(db, current_user.id)]


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectDetailOut:
    """The project with its current documents and its chats."""
    user_id = current_user.id
    summary = _summary_of(db, user_id, project_id)
    chunk_counts = chunks_repo.count_by_document(db, user_id)
    documents = [
        ProjectDocumentOut(
            id=d.id, filename=d.file_name, version=d.version, created_at=d.created_at,
            chunks=chunk_counts.get(d.id, 0),
        )
        for d in documents_repo.list_in_project(db, user_id, project_id)
        if d.is_active
    ]
    chats = [
        ProjectChatOut(
            id=s.id, title=s.title, topic=s.topic or "General", created_at=s.created_at,
            last_message_time=last,
        )
        for s, last, _project_name in sessions_repo.list_with_last_message(db, user_id, project_id)
    ]
    return ProjectDetailOut(**_summary_out(summary).model_dump(), documents=documents, chats=chats)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    """Rename, edit the description or instructions, archive (``archived: true``) or unarchive.
    Only the fields sent change; an empty description or instructions clears it."""
    user_id = current_user.id
    changes = {field: getattr(body, field) for field in body.model_fields_set}
    try:
        project_service.update_project(db, user_id, project_id, changes)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND)
    except ProjectNameTaken:
        raise name_taken_error(str(body.name))
    return _summary_out(_summary_of(db, user_id, project_id))


@router.delete("/{project_id}", response_model=ProjectDeletedOut)
def delete_project(
    project_id: int,
    documents: DocumentsOnDelete = Query(..., description="delete the project's documents, or move them to no project"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> ProjectDeletedOut:
    """Delete the project. ``documents`` is required: the user chooses what happens to its files.
    Its chats always move to no project."""
    try:
        deleted = project_service.delete_project(db, current_user.id, project_id, documents, services.file_storage)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND)
    except FileNameClash as error:
        raise file_name_clash_error(error, "No project")
    return ProjectDeletedOut(
        status="deleted",
        project_id=project_id,
        documents=documents,
        documents_deleted=deleted.documents_deleted,
        documents_unassigned=deleted.documents_unassigned,
        chats_unassigned=deleted.chats_unassigned,
        doc_version=deleted.doc_version,
    )
