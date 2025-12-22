from fastapi import FastAPI, File, UploadFile, Request, Depends, Query, Body
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import os
from logger import setup_logging
from jose import JWTError, jwt
import time
# Service imports
from db import Document, User,init_db,SessionLocal,Message,Session as ChatSession
from document_service import register_document
from indexing_pipeline import IndexingPipeline
from index_builder import IndexBuilder
from keyword_index import BM25KeywordIndex
from retrieval_service import RetrievalService
from auth import (
    get_db, get_password_hash, authenticate_user, verify_password,
    create_access_token, get_current_user,get_current_user_optional
)
from starlette.middleware.sessions import SessionMiddleware
import secrets
from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List, Dict, Any
from enum import Enum
from session_service import (
    get_or_create_session,
    add_message,
    get_recent_messages,
)
from llm_client import LLMClient
from query_decomposer import QueryDecomposer
from semantic_cache import SemanticCache
from context_compressor import SimpleContextCompressor
from fastapi.responses import StreamingResponse
import json
from topic_classifier import topic_classifier
from error_handler import UserFriendlyError
from fastapi.middleware.cors import CORSMiddleware
from concept_models import ConceptMap, ConceptMapNode
# Add these imports to your existing imports
from concept_map_service import get_concept_map_service
from concept_map_schemas import (
    GenerateConceptMapRequest,
    GenerateConceptMapResponse,
    ListConceptMapsResponse,
    ConceptMapDetail,
    DeleteConceptMapResponse,
    SourceStatistics
)
from routes.auth_routes import router as auth_router
app = FastAPI(title="RAG Study Assistant API")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
)
# ADD CORS MIDDLEWARE HERE
# Get allowed origins from environment or use defaults
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000,https://rag-study-assistant-chi.vercel.app"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers
)
app.include_router(auth_router)
logger = setup_logging()
index_builder = IndexBuilder()
bm25_index = BM25KeywordIndex()
indexing_pipeline = IndexingPipeline(index_builder=index_builder, bm25_index=bm25_index)
retrieval_service = RetrievalService(index_builder=index_builder, bm25_index=bm25_index)
llm_client = LLMClient()
query_decomposer = QueryDecomposer()
semantic_cache = SemanticCache(index_builder=index_builder)
compressor = SimpleContextCompressor()

UPLOAD_DIR = "uploads"

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    subject: Optional[str] = None
    file_type: Optional[str] = None  # "pdf", "pptx", "docx"
    start_doc_id: Optional[int] = None
    end_doc_id: Optional[int] = None

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[int] = None
    top_k: int = 8
    mode: str = "detailed"  # "detailed", "quick", "step_by_step"


class ChatResponse(BaseModel):
    answer: str
    session_id: int
    confidence: float
    fallback_used: bool
    grounding_level: Optional[str] = None  # NEW FIELD
    sources: List[Dict[str, Any]]
    followups: Optional[List[str]] = None

class QuizDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class QuizRequest(BaseModel):
    topic: str
    num_questions: int = 5
    difficulty: QuizDifficulty = QuizDifficulty.MEDIUM
    include_answers: bool = False  # True if you want answers

class FeedbackRequest(BaseModel):
    feedback: str              # "up" or "down"
    comment: Optional[str] = None

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    
    @validator('new_password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v
    
# Schema for profile update
class ProfileUpdate(BaseModel):
    name: str

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
):
    # NEW: validate upload
    await validate_upload(file)
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)

    file_location = os.path.join(UPLOAD_DIR, file.filename)
    content = await file.read()
    with open(file_location, "wb") as f:
        f.write(content)

    logger.info(f"Uploaded file saved: {file.filename} by user {current_user.id}")

    # 1) Register document with versioning
    doc = register_document(current_user.id, file_location)

    # 2) Index document for this user (FAISS + BM25)
    num_chunks = indexing_pipeline.index_document(
        file_location,
        user_id=str(current_user.id),
        subject_tags=None,
        document_id=doc.id,
    )

    # ADD THESE 3 LINES:
    current_user.doc_version += 1  # bump version
    db.commit()
    return {
        "filename": file.filename,
        "saved_path": file_location,
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
async def timing_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = (time.perf_counter() - start_time) * 1000
    logger.info(f"REQ {request.method} {request.url.path} {process_time:.1f}ms")
    response.headers["X-Process-Time"] = str(process_time)
    return response

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response Status: {response.status_code} for {request.method} {request.url}")
    return response

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."}
    )

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from auth import (
    get_db,
    get_password_hash,
    authenticate_user,
    create_access_token,
    get_current_user,
)
from db import User
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt


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
):
    # Delete all user data
    db.query(Message).filter(Message.user_id == str(current_user.id)).delete()
    db.query(Session).filter(Session.user_id == str(current_user.id)).delete()
    db.query(Document).filter(Document.user_id == str(current_user.id)).delete()
    db.delete(current_user)
    db.commit()
    
    return {"message": "Account deleted successfully"}

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

def sanitize_query(q: str) -> str:
    q_lower = q.lower()

    # Very simple heuristic: block common injection phrases
    injection_phrases = [
        "ignore previous instructions",
        "you are now",
        "disregard all earlier",
        "system prompt",
    ]
    if any(p in q_lower for p in injection_phrases):
        # Either block or strip; here we block
        raise HTTPException(
            status_code=400,
            detail="Query rejected due to unsafe or prompt-injection-like content.",
        )

    return q
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

@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id_int = current_user.id
    user_id_str = str(current_user.id)
    doc_version = current_user.doc_version  # GET VERSION

    # SAFETY GUARDRAILS - EARLY RETURN
    unsafe_keywords = ["suicide", "kill myself", "nuke", "die","self harm","explosives", "terrorist", "make a bomb"]
    q_lower = body.query.lower()
    if any(k in q_lower for k in unsafe_keywords):
        safe_answer = (
            "I am not able to help with that request. "
            "If you are in distress or in danger, please reach out to a trusted person or "
            "your local emergency services."
        )
        chat_session = get_or_create_session(db, user_id_int, body.session_id, body.query)
        add_message(db, chat_session.id, user_id_int, role="user", content=body.query)
        add_message(db, chat_session.id, user_id_int, role="assistant", content=safe_answer, sources="")
        return ChatResponse(
            answer=safe_answer,
            session_id=chat_session.id,
            confidence=0.0,
            fallback_used=False,
            grounding_level="none",
            sources=[],
            followups=[],
        )
    # 0) Semantic cache lookup
    cached = semantic_cache.lookup(body.query,user_doc_version=doc_version,mode=body.mode)
    if cached is not None:
        return ChatResponse(**cached)

    # 1) Get or create session
    chat_session = get_or_create_session(db, user_id_int, body.session_id, body.query)
    message_count = db.query(Message).filter(Message.session_id == chat_session.id).count()
    # 2) Log user message
    add_message(db, chat_session.id, user_id_int, role="user", content=body.query)
    
    # ✅ TOPIC DETECTION - Auto-tag session on first message or if still "General"
    
    if message_count == 0 or chat_session.topic == "General":
        try:
            topic_result = topic_classifier.classify_topic(body.query)
            if topic_result['confidence'] > 0.3:  # Only update if confident
                chat_session.topic = topic_result['topic']
                db.commit()
                logger.info(
                    f" Session {chat_session.id} tagged: {topic_result['topic']} "
                    f"(confidence: {topic_result['confidence']:.2f})"
                )
        except Exception as e:
            logger.error(f"Topic classification error: {e}")

    # 3) Query decomposition
    subqueries = query_decomposer.decompose(body.query)

    all_context_chunks: List[Dict[str, Any]] = []
    final_confidence = 0.0
    any_fallback = False

    for subq in subqueries:
        retrieval_result = retrieval_service.hybrid_retrieve(
            query=subq,
            user_id=user_id_str,
            doc_version=doc_version,  # PASS VERSION
            top_k=body.top_k,
            rerank_top_k=5,
        )
        child_chunks = retrieval_result["results"]
        # LOG retrieval for inspection
        top_docs = [c["metadata"].get("document_id", "N/A") for c in child_chunks[:3]]
        logger.info("RETRIEVAL subq='%s' conf=%.2f fallback=%s top_docs=%s", 
                    subq[:40], retrieval_result["confidence"], 
                    retrieval_result["fallback_used"], top_docs)
        all_candidates = retrieval_result.get("all_candidates", child_chunks)

        # Parent-document expansion
        parent_chunks = retrieval_service.expand_to_parent_context(
            top_results=child_chunks,
            all_results=all_candidates,
            max_parents=3,
        )

        # Combine child + parents for this sub-query
        all_context_chunks.extend(child_chunks + parent_chunks)

        final_confidence = max(final_confidence, retrieval_result["confidence"])
        any_fallback = any_fallback or retrieval_result["fallback_used"]

    # 4) Contextual compression across all sub-queries
    compressed_context = compressor.compress(all_context_chunks)

    # 5) Get recent history for prompt
    recent_msgs_db = get_recent_messages(db, chat_session.id, limit=10)
    recent_messages = [
        {"role": m.role, "content": m.content}
        for m in recent_msgs_db
    ]

    # NEW: Determine grounding level based on confidence
    if final_confidence >= 0.7:
        grounding_level = "strict"      # Rich context → strict grounding
    elif final_confidence >= 0.3:
        grounding_level = "loose"       # Some context → partial grounding
    else:
        grounding_level = "none"        # No context → full model knowledge

    
    # 6) Build prompt + call LLM with retry and circuit breaker handling
    try:
        prompt = llm_client.build_prompt(
            question=body.query,
            context_chunks=compressed_context,
            recent_messages=recent_messages,
            grounding_level=grounding_level,
            mode=body.mode,
        )
        answer = llm_client.generate_answer(prompt)

        followups = llm_client.generate_followups(body.query, answer, mode=body.mode)

    except RuntimeError as e:
        error_type = UserFriendlyError.classify_error(e)
        error_response = UserFriendlyError.get_message(error_type)
        
        logger.error(f"LLM RuntimeError ({error_type}): {e}")
        # Log assistant's safe message
        add_message(db, chat_session.id, user_id_int, role="assistant", content=error_response['error'], sources="")
        return ChatResponse(
            answer=error_response['error'],
            session_id=chat_session.id,
            confidence=0.0,
            fallback_used=any_fallback,
            grounding_level=grounding_level,
            sources=[],
            followups=[],
        )
    # 7) Log assistant message
    add_message(
        db,
        chat_session.id,
        user_id_int,
        role="assistant",
        content=answer,
        sources=",".join(
            [
                f"{c['metadata'].get('source_type','')}:{c['metadata'].get('file_name', c['metadata'].get('url',''))}"
                for c in compressed_context
            ]
        ),
    )

    resp_dict = {
        "answer": answer,
        "session_id": chat_session.id,
        "confidence": final_confidence,
        "fallback_used": any_fallback,
        "grounding_level": grounding_level,  # NEW FIELD
        "sources": [c["metadata"] for c in compressed_context],
        "followups": followups,
    }

    # 8) Store in semantic cache
    semantic_cache.store(body.query, resp_dict, doc_version,body.mode)

    # NEW: log low-confidence queries for later analysis
    if final_confidence < 0.3:
        logger.warning(
            "LOW_CONFIDENCE_QUERY user_id=%s session_id=%s conf=%.2f query=%r",
            user_id_int, chat_session.id, final_confidence, body.query
        )
    return ChatResponse(**resp_dict)

@app.get("/chat/stream")
async def chat_stream(
    query: str,
    session_id: int = 0,
    top_k: int = 5,
    mode: str = "quick",
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    # Manual token auth
    current_user = None
    if token:
        try:
            from jose import jwt
            from auth import SECRET_KEY, ALGORITHM
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")
            if email:
                current_user = db.query(User).filter(User.email == email).first()
        except:
            pass
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id_int = current_user.id
    user_id_str = str(current_user.id)
    doc_version = getattr(current_user, 'doc_version', 0)

    # Safety check first
    unsafe_keywords = ["explosive", "bomb", "suicide", "self harm"]
    if any(k in query.lower() for k in unsafe_keywords):
        async def safe_stream():
            yield "I'm unable to assist with that request. Please seek help from trusted professionals.\n"
        return StreamingResponse(safe_stream(), media_type="text/plain")

    # Semantic cache (non-blocking lookup)
    cached = semantic_cache.lookup(query, user_doc_version=doc_version, mode=mode)
    if cached:
        # Create/update session for cached response
        chat_session = get_or_create_session(db, user_id_int, session_id, query)
        # ✅ CHECK MESSAGE COUNT BEFORE ADDING
        message_count = db.query(Message).filter(Message.session_id == chat_session.id).count()
        add_message(db, chat_session.id, user_id_int, role="user", content=query)
        
        
        if message_count ==0 or chat_session.topic == "General":
            try:
                topic_result = topic_classifier.classify_topic(query)
                if topic_result['confidence'] > 0.3:
                    chat_session.topic = topic_result['topic']
                    db.commit()
                    logger.info(
                        f" Session {chat_session.id} tagged (cached): {topic_result['topic']} "
                        f"(confidence: {topic_result['confidence']:.2f})"
                    )
            except Exception as e:
                logger.error(f"Topic classification error (cached): {e}")
        async def cached_stream():
            # Send metadata
            metadata = {
                "session_id": chat_session.id,
                "confidence": cached.get("confidence", 100),
                "fallback_used": False,
                "grounding_level": cached.get("grounding_level", "strict"),
                "sources": cached.get("sources", []),
                "mode": mode,
            }
            yield f"data: {json.dumps({'type': 'metadata', 'data': metadata})}\n\n"
            
            # Send cached answer as tokens
            cached_answer = cached.get("answer", "")
            for char in cached_answer:
                yield f"data: {json.dumps({'type': 'token', 'data': char})}\n\n"
            
            # Log assistant message and get ID
            assistant_msg_id = add_message(
                db, chat_session.id, user_id_int, 
                role="assistant", 
                content=cached_answer,
                sources=",".join([str(s.get("file_name", s.get("url", ""))) for s in cached.get("sources", [])])
            )
            
            print(f"DEBUG: Created message with ID: {assistant_msg_id}")  # ← ADD THIS
            # Send message ID
            yield f"data: {json.dumps({'type': 'message_id', 'data': assistant_msg_id})}\n\n"
            print(f"DEBUG: Sent message_id event")  # ← ADD THIS
            # Send DONE
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(cached_stream(), media_type="text/event-stream",
                                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

    # 1) Session + log user message
    chat_session = get_or_create_session(db, user_id_int, session_id, query)
    # ✅ CHECK MESSAGE COUNT BEFORE ADDING
    message_count = db.query(Message).filter(Message.session_id == chat_session.id).count()
    add_message(db, chat_session.id, user_id_int, role="user", content=query)

    #  ADD TOPIC DETECTIon for new response 
    
    if message_count ==0 or chat_session.topic == "General":
        try:
            topic_result = topic_classifier.classify_topic(query)
            if topic_result['confidence'] > 0.3:  # Only update if confident
                chat_session.topic = topic_result['topic']
                db.commit()
                logger.info(
                    f" Session {chat_session.id} tagged: {topic_result['topic']} "
                    f"(confidence: {topic_result['confidence']:.2f})"
                )
        except Exception as e:
            logger.error(f"Topic classification error: {e}")
    

    # 2) Retrieval + processing
    subqueries = query_decomposer.decompose(query)
    all_context_chunks = []
    final_confidence = 0.0
    any_fallback = False

    for subq in subqueries:
        retrieval_result = retrieval_service.hybrid_retrieve(
            query=subq, user_id=user_id_str, doc_version=doc_version,
            top_k=top_k, rerank_top_k=5,
        )
        child_chunks = retrieval_result["results"]
        all_candidates = retrieval_result.get("all_candidates", child_chunks)

        # Parent-document expansion
        parent_chunks = retrieval_service.expand_to_parent_context(
            top_results=child_chunks,
            all_results=all_candidates,
            max_parents=3,
        )
        all_context_chunks.extend(child_chunks + parent_chunks)
        final_confidence = max(final_confidence, retrieval_result["confidence"])
        any_fallback = any_fallback or retrieval_result["fallback_used"]

    compressed_context = compressor.compress(all_context_chunks)
    recent_messages = [{"role": m.role, "content": m.content} for m in get_recent_messages(db, chat_session.id, limit=20)]

    # 3) Determine grounding + build prompt
    grounding_level = "strict" if final_confidence >= 70.0 else "loose" if final_confidence >= 30.0 else "none"

    prompt = llm_client.build_prompt(
        question=query,
        context_chunks=compressed_context,
        recent_messages=recent_messages,
        grounding_level=grounding_level,
        mode=mode,
    )

    # 4) STREAM THE ANSWER
    async def generate():
        try:
            # Send initial metadata
            metadata = {
                "session_id": chat_session.id,
                "confidence": final_confidence,
                "fallback_used": any_fallback,
                "grounding_level": grounding_level,
                "sources": [c["metadata"] for c in compressed_context],
                "mode": mode,
            }
            yield f"data: {json.dumps({'type': 'metadata', 'data': metadata})}\n\n"

            # Log low confidence as failed query
            if final_confidence < 30.0:  # Threshold for "low confidence"
                from db import FailedQuery
                failed_query = FailedQuery(
                    user_id=str(user_id_int),
                    session_id=chat_session.id,
                    query=query,
                    confidence=final_confidence,
                    feedback=None,
                    reason='low_confidence',
                    comment=f"Automatic log: confidence={final_confidence}",
                    timestamp=datetime.datetime.utcnow()
                )
                db.add(failed_query)
                db.commit()

            # Stream tokens
            full_answer = ""
            for token in llm_client.stream_answer(prompt):
                full_answer += token
                yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

            # Log assistant message and get ID
            assistant_msg_id = add_message(
                db, chat_session.id, user_id_int, 
                role="assistant", 
                content=full_answer,
                sources=",".join([c["metadata"].get("file_name", c["metadata"].get("url", "")) for c in compressed_context])
            )

            # Send message ID to frontend
            yield f"data: {json.dumps({'type': 'message_id', 'data': assistant_msg_id})}\n\n"

            # Final message
            yield "data: [DONE]\n\n"

            # Cache the response
            resp_dict = {
                "answer": full_answer,
                "session_id": chat_session.id,
                "confidence": final_confidence,
                "fallback_used": any_fallback,
                "grounding_level": grounding_level,
                "sources": [c["metadata"] for c in compressed_context],
                "followups": [],
            }
            semantic_cache.store(query, resp_dict, doc_version, mode)

        except RuntimeError as e:
            error_type = UserFriendlyError.classify_error(e)
            error_response = UserFriendlyError.get_message(error_type)
            
            logger.error(f"Stream RuntimeError ({error_type}): {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': error_response['error']})}\n\n"
        except Exception as e:
            logger.error(f"Unexpected stream error: {e}")
            error_response = UserFriendlyError.get_message("unknown")
            yield f"data: {json.dumps({'type': 'error', 'data': error_response['error']})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )



@app.post("/quiz")
async def generate_quiz(
    body: QuizRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate quiz questions from internet knowledge (not user documents)"""
    
    logger.info(f"Generating {body.difficulty} quiz for user {current_user.id}, topic: {body.topic}")

    # Build difficulty-specific prompt
    difficulty_instructions = {
        "easy": "basic, straightforward questions suitable for beginners",
        "medium": "moderate difficulty questions requiring understanding of key concepts",
        "hard": "advanced, challenging questions requiring deep understanding and critical thinking"
    }
    
    difficulty_desc = difficulty_instructions[body.difficulty]
    
    # Build prompt for internet-based quiz
    if body.include_answers:
        prompt = f"""You are an expert quiz creator. Generate {body.num_questions} multiple-choice questions about "{body.topic}".

Difficulty Level: {body.difficulty.upper()} - Create {difficulty_desc}.
IMPORTANT: Use plain text only. Do NOT use markdown formatting (no **, ##, or other symbols).

Format each question EXACTLY like this:

Question X: [question text]
A) [option A]
B) [option B]
C) [option C]
D) [option D]
Correct Answer: [letter]
Explanation: [brief explanation]

Make the questions educational and accurate. Include varied topics within {body.topic}."""
    else:
        prompt = f"""You are an expert quiz creator. Generate {body.num_questions} multiple-choice questions about "{body.topic}".

Difficulty Level: {body.difficulty.upper()} - Create {difficulty_desc}.
IMPORTANT: Use plain text only. Do NOT use markdown formatting (no **, ##, or other symbols).

Format each question as:
Question X: [question text]
A) [option A]
B) [option B]
C) [option C]
D) [option D]

Question 2: [question text]
A) [option A]
B) [option B]
C) [option C]
D) [option D]

Do NOT include answers. Make the questions educational and accurate."""

    try:
        quiz_text = llm_client.generate_answer(prompt)
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
from db import Message
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
    from db import FailedQuery
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
    from db import FailedQuery
    
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
        service = get_concept_map_service()
        
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
        service = get_concept_map_service()
        
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
        service = get_concept_map_service()
        
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
        service = get_concept_map_service()
        
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
        service = get_concept_map_service()
        
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
