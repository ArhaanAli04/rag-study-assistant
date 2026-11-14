import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_services
from app.db.models import User
from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.ingestion.upload_storage import UPLOAD_ROOT, UnsafeUploadPath, display_name, file_extension, new_upload_path
from app.retrieval.embeddings import EmbeddingError
from app.schemas.documents import SearchRequest
from app.services import document_service
from app.services.container import Services
from app.services.document_service import register_upload

logger = logging.getLogger("rag_assistant.api.documents")
router = APIRouter(tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".docx"}
MAX_FILE_SIZE_MB = 50


async def validate_upload(file: UploadFile) -> None:
    # Extension check
    filename = file.filename or ""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    ext = f".{ext}"
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Size check: read stream into memory once for size (ok for <= 50MB)
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Max {MAX_FILE_SIZE_MB} MB."
        )

    # Reset file for later processing
    file.file.seek(0)


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    await validate_upload(file)
    original_name = display_name(file.filename)
    try:
        stored_path = new_upload_path(UPLOAD_ROOT, current_user.id, file_extension(original_name))
    except UnsafeUploadPath:
        logger.error(f"Refused upload path for user {current_user.id}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not store the file.")
    file_location = str(stored_path)
    content = await file.read()
    with open(file_location, "wb") as f:
        f.write(content)

    logger.info(f"Uploaded file saved: {original_name} as {file_location} by user {current_user.id}")

    registered = register_upload(current_user.id, file_location, original_name, UPLOAD_ROOT, file_size=len(content))
    doc = registered.document
    if not registered.needs_indexing:
        # I6: an identical re-upload that is already indexed. Re-indexing would re-embed every chunk,
        # and a doc_version bump would empty the user's caches for nothing.
        return {
            "filename": original_name,
            "document_id": doc.id,
            "status": registered.status,
            "version": doc.version,
            "chunks_indexed": 0,
            "doc_version": current_user.doc_version,
        }

    try:
        indexed = services.indexing_service.index_document(
            db,
            file_path=doc.file_path,
            user_id=current_user.id,
            document_id=doc.id,
            document_version=doc.version,
            file_name=original_name,
        )
    except EmbeddingError:
        # Nothing was written: the row stays without chunks, and re-uploading the file indexes it.
        db.rollback()
        logger.warning("Indexing document %s of user %s failed", doc.id, current_user.id, exc_info=True)
        raise HTTPException(
            status_code=502, detail="The file was saved but could not be indexed. Please upload it again."
        )

    # One commit for the chunks and the version bump: caches never see the new version without them.
    current_user.doc_version += 1
    db.commit()
    return {
        "filename": original_name,
        "document_id": doc.id,
        "status": registered.status,
        "version": doc.version,
        "chunks_indexed": indexed.chunks_indexed,
        "doc_version": current_user.doc_version
    }


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    deleted = document_service.delete_document(db, current_user.id, doc_id, UPLOAD_ROOT)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # The document set changed: every cache keyed on doc_version stops matching, so the deleted
    # file is never cited again, not even from a cached answer.
    current_user.doc_version += 1
    db.commit()

    return {
        "status": "deleted",
        "document_id": doc_id,
        "versions_deleted": deleted.versions,
        "doc_version": current_user.doc_version,
    }


@router.get("/documents")
async def get_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """The user's current documents, each with its size and how many searchable chunks it has."""
    chunk_counts = chunks_repo.count_by_document(db, current_user.id)  # one grouped query (CO6)
    result = []
    for doc in documents_repo.list_active(db, current_user.id):
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
        })

    return result


@router.post("/search")
async def semantic_search(
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
