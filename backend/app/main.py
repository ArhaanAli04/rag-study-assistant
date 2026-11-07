from fastapi import FastAPI, File, UploadFile, Request, Depends, Query, Body
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import os
from app.core.logging import setup_logging
from jose import JWTError, jwt
import time
# Service imports
from app.db.database import Document, User,init_db,SessionLocal,Message,Session as ChatSession
from app.services.document_service import register_upload
from app.ingestion.indexing_pipeline import IndexingPipeline
from app.retrieval.index_builder import IndexBuilder
from app.retrieval.keyword_index import BM25KeywordIndex
from app.retrieval.retrieval_service import RetrievalService
from app.api.deps import get_current_user, get_db, get_user_from_query_token
from app.services.account_service import authenticate_user
from app.core.security import create_access_token, get_password_hash, verify_password
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import settings
from app.core.request_id import RequestIdMiddleware
from typing import Optional, List, Dict, Any, Awaitable, Callable
from app.schemas.auth import PasswordChange, UserCreate
from app.schemas.documents import SearchRequest
from app.schemas.feedback import FeedbackRequest
from app.schemas.quiz import QuizRequest
from app.schemas.users import ProfileUpdate
from app.generation.llm_client import LLMClient
from app.retrieval.query_decomposer import QueryDecomposer
from app.services.caches.semantic_cache import SemanticCache
from app.retrieval.context_compressor import SimpleContextCompressor
from fastapi.responses import StreamingResponse
from app.generation.topic_classifier import TopicClassifier
from app.generation.concept_extractor import ConceptExtractor
from app.core.gemini import build_gemini_client
from app.retrieval.embeddings import EmbeddingService
from app.retrieval.concept_map_retriever import ConceptMapRetriever
from app.services.caches.query_cache import QueryCache
from app.services.caches.web_cache import WebCache
import redis
from app.services.chat_pipeline import ChatPipeline
from app.services.quiz_service import generate_quiz_text
from app.services.account_service import delete_user_account
from dataclasses import asdict
from app.ingestion.upload_storage import UPLOAD_ROOT, UnsafeUploadPath, display_name, file_extension, new_upload_path
from fastapi.middleware.cors import CORSMiddleware
from app.db.models.concept_map import ConceptMap, ConceptMapNode
# Add these imports to your existing imports
from app.services.concept_map_service import ConceptMapService
from app.schemas.concept_maps import (
    GenerateConceptMapRequest,
    GenerateConceptMapResponse,
    ListConceptMapsResponse,
    ConceptMapDetail,
    DeleteConceptMapResponse,
    SourceStatistics
)
from app.api.routes.auth import router as auth_router
app = FastAPI(title="RAG Study Assistant API")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.JWT_SECRET_KEY.get_secret_value()
)
ALLOWED_ORIGINS = settings.allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers
)
app.include_router(auth_router)
logger = setup_logging()
gemini_client = build_gemini_client()
index_builder = IndexBuilder(EmbeddingService(gemini_client))
bm25_index = BM25KeywordIndex()
indexing_pipeline = IndexingPipeline(index_builder=index_builder, bm25_index=bm25_index)
redis_client = redis.from_url(settings.redis_url)
retrieval_service = RetrievalService(
    index_builder=index_builder,
    bm25_index=bm25_index,
    query_cache=QueryCache(redis_client),
    web_cache=WebCache(redis_client),
)
llm_client = LLMClient(gemini_client)
topic_classifier = TopicClassifier(gemini_client)
query_decomposer = QueryDecomposer()
semantic_cache = SemanticCache(index_builder=index_builder)
compressor = SimpleContextCompressor()
concept_map_service = ConceptMapService(
    ConceptMapRetriever(retrieval_service), ConceptExtractor(gemini_client)
)
chat_pipeline = ChatPipeline(
    retrieval_service=retrieval_service,
    llm_client=llm_client,
    topic_classifier=topic_classifier,
    semantic_cache=semantic_cache,
    query_decomposer=query_decomposer,
    compressor=compressor,
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}

ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".docx"}
MAX_FILE_SIZE_MB = 50

async def validate_upload(file: UploadFile):
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

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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

    doc = register_upload(current_user.id, file_location, original_name, UPLOAD_ROOT)

    num_chunks = indexing_pipeline.index_document(
        doc.file_path,
        user_id=str(current_user.id),
        subject_tags=None,
        document_id=doc.id,
        file_name=original_name,
    )

    current_user.doc_version += 1
    db.commit()
    return {
        "filename": original_name,
        "document_id": doc.id,
        "chunks_indexed": num_chunks,
        "doc_version": current_user.doc_version
    }

@app.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.user_id == str(current_user.id)
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # remove from DB
    db.delete(doc)
    db.commit()

    # bump doc_version for this user to invalidate caches
    current_user.doc_version += 1
    db.commit()

    # (Optional) remove file from disk
    # if doc.path and os.path.exists(doc.path): os.remove(doc.path)

    return {"status": "deleted", "document_id": doc_id, "doc_version": current_user.doc_version}

@app.get("/documents")
async def get_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all documents for current user"""
    
    documents = (
        db.query(Document)
        .filter(
            Document.user_id == str(current_user.id),  # Convert to string
            Document.is_active == True  # Only active documents
        )
        .order_by(desc(Document.id))  # Order by ID since no created_at
        .all()
    )
    
    result = []
    for doc in documents:
        # Get file size if file exists
        file_size = None
        if doc.file_path and os.path.exists(doc.file_path):
            file_size = os.path.getsize(doc.file_path)
        
        result.append({
            "id": doc.id,
            "filename": doc.file_name,  # ✅ Use file_name
            "path": doc.file_path,      # ✅ Use file_path
            "created_at": None,  # No timestamp field in your model
            "file_size": file_size,
            "version": doc.version,
        })
    
    return result

@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    # Path only, never request.url: /chat/stream carries the JWT in ?token= (G8).
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = (time.perf_counter() - start_time) * 1000
    logger.info(f"REQ {request.method} {request.url.path} {response.status_code} {process_time:.1f}ms")
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Registered last on purpose: the last middleware added is the outermost, so the ID is already
# set when log_requests and CORS run, and stays set for the whole SSE stream.
app.add_middleware(RequestIdMiddleware)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."}
    )

from fastapi import HTTPException, status


@app.post("/register")
async def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = User(email=user.email, hashed_password=get_password_hash(user.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"id": new_user.id, "email": new_user.email}

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change user password after verifying current password
    """
     # Check if user is OAuth user (no password)
    if not current_user.hashed_password or current_user.oauth_provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change password for OAuth users. Manage your password through Google."
        )
    
    # Verify current password
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Check if new password is same as current
    if verify_password(password_data.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )
    
    # Hash and update new password
    current_user.hashed_password = get_password_hash(password_data.new_password)
    db.commit()
    
    return {
        "message": "Password changed successfully",
        "email": current_user.email
    }

@app.get("/me")
async def read_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email}

# Get user profile
@app.get("/user/profile")
async def get_profile(
    current_user: User = Depends(get_current_user)
):
    return {
        "email": current_user.email,
        "name": current_user.name if hasattr(current_user, 'name') and current_user.name else current_user.username,
        "username": current_user.username if hasattr(current_user, 'username') else "",
        "profile_picture": current_user.profile_picture if hasattr(current_user, 'profile_picture') else None,
        "oauth_provider": current_user.oauth_provider if hasattr(current_user, 'oauth_provider') else None,
        "created_at": current_user.created_at if hasattr(current_user, 'created_at') else None
    }

# Update user profile
@app.put("/user/profile")
async def update_profile(
    profile: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Update user name
    current_user.name = profile.name
    db.commit()
    
    return {
        "message": "Profile updated successfully",
        "email": current_user.email,
        "name": current_user.name
    }

@app.get("/user/stats")
async def get_user_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user statistics for profile"""
    
    # Count documents uploaded by user
    document_count = db.query(Document).filter(
        Document.user_id == str(current_user.id),
        Document.is_active == True
    ).count()
    
    # Get account creation date
    created_at = current_user.created_at if hasattr(current_user, 'created_at') and current_user.created_at else None
    
    return {
        "member_since": created_at.isoformat() if created_at else None,
        "plan": "Free",  # Can be dynamic later if you add paid plans
        "documents_uploaded": document_count,
        "documents_limit": 10,  # Free plan limit
        "email": current_user.email,
        "name": current_user.name if hasattr(current_user, 'name') else ""
    }

# Delete account
@app.delete("/user/delete")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    summary = delete_user_account(
        db,
        current_user,
        indexes=[index_builder.get_index(), bm25_index],
        semantic_cache=semantic_cache,
        retrieval_cache=retrieval_service,
        upload_root=UPLOAD_ROOT,
    )
    return {"message": "Account deleted successfully", "deleted": asdict(summary)}

@app.post("/search")
async def semantic_search(
    body: SearchRequest,
    current_user: User = Depends(get_current_user),
):
    # Build filters from request metadata
    filters: Dict[str, Any] = {"user_id": str(current_user.id)}
    if body.subject:
        filters["subject_tags"] = body.subject
    if body.file_type:
        filters["doc_type"] = body.file_type
    # For now, we ignore start_doc_id/end_doc_id or handle them at DB level later.

    results = retrieval_service.semantic_search(
        query=body.query,
        user_id=str(current_user.id),
        top_k=body.top_k,
        # If your semantic_search/index_builder.search already accept filters,
        # you can thread `filters` in there; otherwise keep as is and only
        # user_id filtering happens.
        filters=filters
    )
    return {"results": results}

from sqlalchemy import func, desc
@app.get("/sessions")
async def get_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):  
    """Get all chat sessions ordered by most recent message"""
    
    # Subquery to get the latest message timestamp for each session
    latest_message = (
        db.query(
            Message.session_id,
            func.max(Message.timestamp).label('last_message_time')
        )
        .group_by(Message.session_id)
        .subquery()
    )
    
    # Query sessions with their latest message time
    sessions_with_time = (
        db.query(
            ChatSession,
            latest_message.c.last_message_time
        )
        .outerjoin(latest_message, ChatSession.id == latest_message.c.session_id)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(desc(latest_message.c.last_message_time).nulls_last())
        .all()
    )
    
    # Build response
    result = []
    for session, last_msg_time in sessions_with_time:
        result.append({
            "id": session.id,
            "title": session.title,
            "topic": session.topic or "General",  # ✅ ADD TOPIC
            "created_at": session.created_at.isoformat() + 'Z' if session.created_at else None,
            "last_message_time": last_msg_time.isoformat() + 'Z' if last_msg_time else None,
        })
    
    return result


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all messages in a session."""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.timestamp.asc())  # ← Changed from created_at
        .all()
    )
    
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources":  m.sources.split(',') if m.sources else [],
            "created_at": m.timestamp.isoformat(),  # ← Use timestamp but return as created_at
        }
        for m in messages
    ]

@app.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a chat session"""
    
    # Find the session
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Delete associated messages first (if not cascade deleted)
    db.query(Message).filter(Message.session_id == session_id).delete()
    
    # Delete the session
    db.delete(session)
    db.commit()
    
    return {"message": "Session deleted successfully"}

@app.patch("/sessions/{session_id}/rename")
async def rename_session(
    session_id: int,
    new_title: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a chat session"""
    
    # Validate title
    if not new_title or len(new_title.strip()) == 0:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    
    if len(new_title) > 100:
        raise HTTPException(status_code=400, detail="Title too long (max 100 characters)")
    
    # Find the session
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update title
    session.title = new_title.strip()
    db.commit()
    db.refresh(session)
    
    return {
        "message": "Session renamed successfully",
        "session": {
            "id": session.id,
            "title": session.title,
            "topic": session.topic or "General",
            "created_at": session.created_at.isoformat() + 'Z' if session.created_at else None,
        }
    }

@app.get("/chat/stream")
async def chat_stream(
    query: str,
    session_id: int = 0,
    top_k: int = 5,
    mode: str = "quick",
    current_user: User = Depends(get_user_from_query_token),
    db: Session = Depends(get_db),
):
    chat = chat_pipeline.answer(db, current_user, query, session_id, top_k, mode)
    return StreamingResponse(chat.events, media_type="text/event-stream", headers=chat.headers)


@app.post("/quiz")
async def generate_quiz(
    body: QuizRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate quiz questions from internet knowledge (not user documents)"""
    logger.info(f"Generating {body.difficulty} quiz for user {current_user.id}, topic: {body.topic}")
    try:
        quiz_text = generate_quiz_text(
            llm_client, body.topic, body.num_questions, body.difficulty.value, body.include_answers
        )
    except RuntimeError as e:
        logger.error(f"LLM error in /quiz: {e}")
        raise HTTPException(
            status_code=503,
            detail="Quiz generation service is temporarily unavailable."
        )

    return {
        "topic": body.topic,
        "difficulty": body.difficulty,
        "num_questions": body.num_questions,
        "questions": quiz_text,
        "has_answers": body.include_answers,
    }

from fastapi import HTTPException
from app.db.database import Message
import datetime
@app.post("/messages/{message_id}/feedback")
async def submit_feedback(
    message_id: int,
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit thumbs up/down feedback for a message"""
    from sqlalchemy import text
    from app.db.database import FailedQuery
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
    
    # NEW: Log failed query if thumbs down
    if body.feedback == 'down':
        # Find the user query that led to this answer
        user_msg = db.query(Message).filter(
            Message.session_id == msg.session_id,
            Message.role == 'user',
            Message.id < msg.id
        ).order_by(Message.id.desc()).first()
        
        if user_msg:
            # Create failed query entry
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

@app.get("/analytics/failed-queries")
async def get_failed_queries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50
):
    """Get recent failed queries for analysis"""
    from app.db.database import FailedQuery
    
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


# CONCEPT MAP ENDPOINTS

@app.post(
    "/api/concepts/generate",
    response_model=GenerateConceptMapResponse,
    tags=["Concept Maps"]
)
async def generate_concept_map(
    request: GenerateConceptMapRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a new concept map
    
    - Retrieves context from documents and/or web
    - Extracts concepts using LLM
    - Saves to database
    - Returns structured concept map
    """
    try:
        service = concept_map_service
        
        result = service.generate_concept_map(
            topic=request.topic,
            user_id=current_user.id,
            db=db,
            use_documents=request.use_documents,
            use_web=request.use_web,
            max_concepts=request.max_concepts,
            max_edges=request.max_edges
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate concept map: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate concept map")


@app.get(
    "/api/concepts/maps",
    response_model=ListConceptMapsResponse,
    tags=["Concept Maps"]
)
async def list_concept_maps(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all concept maps for the current user
    
    - Ordered by creation date (newest first)
    - Includes summary information
    - Paginated results
    """
    try:
        service = concept_map_service
        
        maps = service.list_user_concept_maps(
            user_id=current_user.id,
            db=db,
            limit=limit,
            offset=offset
        )
        
        return {
            "maps": maps,
            "total": len(maps)
        }
        
    except Exception as e:
        logger.error(f"Failed to list concept maps: {e}")
        raise HTTPException(status_code=500, detail="Failed to list concept maps")


@app.get(
    "/api/concepts/maps/{map_id}",
    response_model=ConceptMapDetail,
    tags=["Concept Maps"]
)
async def get_concept_map(
    map_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get full details of a specific concept map
    
    - Includes all nodes and edges
    - Includes source information
    - Verifies user ownership
    """
    try:
        service = concept_map_service
        
        concept_map = service.get_concept_map_by_id(
            map_id=map_id,
            user_id=current_user.id,
            db=db
        )
        
        if not concept_map:
            raise HTTPException(status_code=404, detail="Concept map not found")
        
        return concept_map
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get concept map: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve concept map")


@app.delete(
    "/api/concepts/maps/{map_id}",
    response_model=DeleteConceptMapResponse,
    tags=["Concept Maps"]
)
async def delete_concept_map(
    map_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a concept map
    
    - Verifies user ownership
    - Deletes map and associated nodes
    - Returns confirmation
    """
    try:
        service = concept_map_service
        
        deleted = service.delete_concept_map(
            map_id=map_id,
            user_id=current_user.id,
            db=db
        )
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Concept map not found")
        
        return {
            "message": "Concept map deleted successfully",
            "map_id": map_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete concept map: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete concept map")


@app.get(
    "/api/concepts/statistics",
    response_model=SourceStatistics,
    tags=["Concept Maps"]
)
async def get_concept_map_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get statistics about user's concept maps
    
    - Total maps created
    - Source breakdown (documents vs web)
    - Average confidence scores
    - Node and edge counts
    """
    try:
        service = concept_map_service
        
        stats = service.get_source_statistics(
            user_id=current_user.id,
            db=db
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")






@app.on_event("startup")
async def on_startup():
    init_db()
    logger.info("Database initialized")
