import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_services
from app.api.routes.projects import (
    ARCHIVED_PROJECT,
    PROJECT_NOT_FOUND,
    file_name_clash_error,
    require_project_target,
)
from app.db.models import User
from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.repositories import users as users_repo
from app.ingestion.upload_storage import StorageError, UnsafeUploadPath, display_name
from app.retrieval.embeddings import EmbeddingError
from app.schemas.documents import SearchRequest
from app.schemas.projects import MoveToProject
from app.services import document_service, project_service
from app.services.container import Services
from app.services.document_service import register_upload
from app.services.indexing_service import DocumentDeleted
from app.services.project_service import DocumentNotFound, FileNameClash, ProjectArchived, ProjectNotFound

logger = logging.getLogger("rag_assistant.api.documents")
router = APIRouter(tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".docx"}
MAX_FILE_SIZE_MB = 50


def read_validated_upload(file: UploadFile) -> bytes:
    """The upload's bytes, once its extension and size are checked.

    FastAPI has already received the whole body into file.file (memory or a temp file), so this
    sync read waits on no network; the route is a plain def and runs in the threadpool anyway.
    """
    filename = file.filename or ""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    ext = f".{ext}"
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content = file.file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Max {MAX_FILE_SIZE_MB} MB."
        )
    return content


@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    project_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    # Plain values: index_document ends the session's transaction, which expires current_user.
    user_id, doc_version = current_user.id, current_user.doc_version
    # Before reading the body: a refused project stores and indexes nothing.
    require_project_target(db, user_id, project_id)
    content = read_validated_upload(file)
    original_name = display_name(file.filename)
    try:
        registered = register_upload(
            user_id, content, original_name, services.file_storage, project_id=project_id
        )
    except (StorageError, UnsafeUploadPath):
        logger.error("Could not store an upload of user %s", user_id, exc_info=True)
        raise HTTPException(status_code=503, detail="Could not store the file right now. Please try again.")
    doc = registered.document
    logger.info("Upload %s by user %s: %s, stored as %s", original_name, user_id, registered.status, doc.file_path)
    if not registered.needs_indexing:
        # I6: an identical re-upload that is already indexed. Re-indexing would re-embed every chunk,
        # and a doc_version bump would empty the user's caches for nothing.
        return {
            "filename": original_name,
            "document_id": doc.id,
            "status": registered.status,
            "version": doc.version,
            "chunks_indexed": 0,
            "doc_version": doc_version,
        }

    try:
        # Parsers read a file: the stored one locally, a temporary download from object storage.
        with services.file_storage.local_copy(doc.file_path) as local_path:
            indexed = services.indexing_service.index_document(
                db,
                file_path=str(local_path),
                user_id=user_id,
                document_id=doc.id,
                document_version=doc.version,
                file_name=original_name,
                superseded_document_ids=registered.superseded_document_ids,
            )
    except (EmbeddingError, StorageError):
        # Nothing was written: the row stays without chunks, and re-uploading the file indexes it.
        db.rollback()
        logger.warning("Indexing document %s of user %s failed", doc.id, user_id, exc_info=True)
        raise HTTPException(
            status_code=502, detail="The file was saved but could not be indexed. Please upload it again."
        )
    except DocumentDeleted:
        # Nothing was written, and the delete removed the row and its stored files.
        db.rollback()
        logger.info("Document %s of user %s was deleted while it was being indexed", doc.id, user_id)
        raise HTTPException(
            status_code=409, detail="The file was deleted while it was being indexed. Upload it again to use it."
        )

    # One commit for the chunks and the version bump: caches never see the new version without them.
    new_doc_version = users_repo.increment_doc_version(db, user_id)
    db.commit()
    return {
        "filename": original_name,
        "document_id": doc.id,
        "status": registered.status,
        "version": doc.version,
        "chunks_indexed": indexed.chunks_indexed,
        "doc_version": new_doc_version,
    }


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    user_id = current_user.id  # delete_document commits, which expires current_user
    deleted = document_service.delete_document(db, user_id, doc_id, services.file_storage)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # The document set changed: every cache keyed on doc_version stops matching, so the deleted
    # file is never cited again, not even from a cached answer.
    new_doc_version = users_repo.increment_doc_version(db, user_id)
    db.commit()

    return {
        "status": "deleted",
        "document_id": doc_id,
        "versions_deleted": deleted.versions,
        "doc_version": new_doc_version,
    }


@router.patch("/documents/{doc_id}")
def move_document(
    doc_id: int,
    body: MoveToProject,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Move a document, with all its versions, to one of the user's projects (or to no project)."""
    user_id = current_user.id  # move_document commits, which expires current_user
    try:
        doc_version = project_service.move_document(db, user_id, doc_id, body.project_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="Document not found")
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND)
    except ProjectArchived:
        raise HTTPException(status_code=409, detail=ARCHIVED_PROJECT)
    except FileNameClash as error:
        raise file_name_clash_error(error, "That project" if body.project_id is not None else "No project")
    return {"status": "moved", "document_id": doc_id, "project_id": body.project_id, "doc_version": doc_version}


@router.get("/documents")
def get_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """The user's current documents, each with its size, project and searchable chunk count."""
    chunk_counts = chunks_repo.count_by_document(db, current_user.id)  # one grouped query (CO6)
    result = []
    for doc, project_name in documents_repo.list_active_with_project(db, current_user.id):
        file_size = doc.file_size
        # Rows from before Day 15 have no stored size; their local file may still say.
        if file_size is None and doc.file_path and os.path.isfile(doc.file_path):
            file_size = os.path.getsize(doc.file_path)

        result.append({
            "id": doc.id,
            "filename": doc.file_name,
            "path": doc.file_path,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "file_size": file_size,
            "version": doc.version,
            # 0 = listed but not searchable (indexing failed, or a pre-Day 15 row): re-upload it.
            "chunks": chunk_counts.get(doc.id, 0),
            "project_id": doc.project_id,
            "project_name": project_name,
        })

    return result


@router.post("/search")
def semantic_search(
    body: SearchRequest,
    current_user: User = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    # The user filter is part of the query itself; these narrow it further (jsonb containment).
    metadata_filter: Dict[str, Any] = {}
    if body.subject:
        metadata_filter["subject_tags"] = body.subject
    if body.file_type:
        metadata_filter["doc_type"] = body.file_type

    results = services.retrieval_service.semantic_search(
        query=body.query,
        user_id=str(current_user.id),
        top_k=body.top_k,
        metadata_filter=metadata_filter,
    )
    return {"results": results}
