from fastapi import FastAPI, File, UploadFile, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import os
from logger import setup_logging
from jose import JWTError, jwt
import time
# Service imports
from db import Document, User,init_db
from document_service import register_document
from indexing_pipeline import IndexingPipeline
from index_builder import IndexBuilder
from keyword_index import BM25KeywordIndex
from retrieval_service import RetrievalService
from auth import (
    get_db, get_password_hash, authenticate_user, 
    create_access_token, get_current_user
)
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

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

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="RAG Study Assistant API")
# ADD CORS MIDDLEWARE HERE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers
)
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

class QuizRequest(BaseModel):
    topic: Optional[str] = None
    num_questions: int = 5
    mode: str = "detailed"  # how verbose explanations should be if you include answers

class FeedbackRequest(BaseModel):
    feedback: str              # "up" or "down"
    comment: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    password: str

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
        Document.user_id == current_user.id
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

@app.get("/me")
async def read_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email}


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

    # 2) Log user message
    add_message(db, chat_session.id, user_id_int, role="user", content=body.query)
    
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
        # Log the error and return a user-friendly message
        logger.error(f"LLM error during answer or follow-up generation: {e}")
        friendly = (
            "The answer service is temporarily unavailable due to an internal error. "
            "Please try again later."
        )
        # Log assistant's safe message
        add_message(db, chat_session.id, user_id_int, role="assistant", content=friendly, sources="")
        return ChatResponse(
            answer=friendly,
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

@app.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id_int = current_user.id
    user_id_str = str(current_user.id)
    doc_version = getattr(current_user, 'doc_version', 0)

    # Safety check first
    unsafe_keywords = ["explosive", "bomb", "suicide", "self harm"]
    if any(k in body.query.lower() for k in unsafe_keywords):
        async def safe_stream():
            yield "I'm unable to assist with that request. Please seek help from trusted professionals.\n"
        return StreamingResponse(safe_stream(), media_type="text/plain")

    # Semantic cache (non-blocking lookup)
    cached = semantic_cache.lookup(body.query, user_doc_version=doc_version, mode=body.mode)
    if cached:
        async def cached_stream():
            yield f"data: {json.dumps(cached)}\n\n"
            yield "data: [CACHE_HIT]\n\n"
        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    # 1) Session + log user message
    chat_session = get_or_create_session(db, user_id_int, body.session_id, body.query)
    add_message(db, chat_session.id, user_id_int, role="user", content=body.query)

    # 2) Retrieval + processing (same as regular /chat)
    subqueries = query_decomposer.decompose(body.query)
    all_context_chunks = []
    final_confidence = 0.0
    any_fallback = False

    for subq in subqueries:
        retrieval_result = retrieval_service.hybrid_retrieve(
            query=subq, user_id=user_id_str, doc_version=doc_version,
            top_k=body.top_k, rerank_top_k=5,
        )
        child_chunks = retrieval_result["results"]
        all_candidates = retrieval_result.get("all_candidates", child_chunks)

        # Parent-document expansion
        parent_chunks = retrieval_service.expand_to_parent_context(
            top_results=child_chunks,
            all_results=all_candidates,
            max_parents=3,
        )
        # ... same retrieval logic as /chat ...
        all_context_chunks.extend(child_chunks + parent_chunks)
        final_confidence = max(final_confidence, retrieval_result["confidence"])
        any_fallback = any_fallback or retrieval_result["fallback_used"]

    compressed_context = compressor.compress(all_context_chunks)
    recent_messages = [{"role": m.role, "content": m.content} for m in get_recent_messages(db, chat_session.id, limit=20)]

    # 3) Determine grounding + build prompt
    grounding_level = "strict" if final_confidence >= 0.7 else "loose" if final_confidence >= 0.3 else "none"

    prompt = llm_client.build_prompt(
        question=body.query,
        context_chunks=compressed_context,
        recent_messages=recent_messages,
        grounding_level=grounding_level,
        mode=body.mode,
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
                "mode": body.mode,
            }
            yield f"data: {json.dumps({'type': 'metadata', 'data': metadata})}\n\n"

            # Stream tokens
            async for token in llm_client.stream_answer(prompt):
                yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

            # Final message
            yield "data: [DONE]\n\n"

            # Log assistant message
            answer = ""  # Could collect full answer if needed
            add_message(db, chat_session.id, user_id_int, role="assistant", content="[STREAMED]", sources="")

            # Cache the response (you'd need to collect full answer first)
            # semantic_cache.store(body.query, metadata, doc_version, body.mode)

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': 'Stream failed. Please try again.'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@app.post("/quiz")
async def generate_quiz(
    body: QuizRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id_str = str(current_user.id)
    doc_version = current_user.doc_version

    # Simple retrieval: use hybrid_retrieve on topic or generic "generate quiz"
    query = body.topic or "generate quiz questions from my study materials"
    retrieval_result = retrieval_service.hybrid_retrieve(
        query=query,
        user_id=user_id_str,
        doc_version=doc_version,
        top_k=body.num_questions * 3,
        rerank_top_k=body.num_questions * 2,
    )
    candidates = retrieval_result["results"]
    compressed_context = compressor.compress(candidates)

    # Build a quiz-specific prompt
    context_text = "\n\n".join(c["text"] for c in compressed_context)
    prompt = (
        "You are an AI tutor. Using ONLY the information in the following study snippets, "
        "generate a quiz for the student.\n"
        "Create {n} multiple-choice or short-answer questions that test understanding of the material.\n"
        "Do not include the answers, only the questions.\n\n"
        "Study snippets:\n"
        f"{context_text}\n\n"
        "Now write the questions, numbered:\n"
    ).format(n=body.num_questions)

    try:
        quiz_text = llm_client.generate_answer(prompt)
    except RuntimeError as e:
        logger.error(f"LLM error in /quiz: {e}")
        raise HTTPException(status_code=503, detail="Quiz generation service is temporarily unavailable.")

    return {
        "questions": quiz_text,
        "sources": [c["metadata"] for c in compressed_context],
    }

from fastapi import HTTPException
from db import Message
@app.post("/messages/{message_id}/feedback")
async def submit_feedback(
    message_id: int,
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate feedback value
    if body.feedback not in ("up", "down"):
        raise HTTPException(status_code=400, detail="feedback must be 'up' or 'down'")

    msg = db.query(Message).filter(
        Message.id == message_id,
        Message.user_id == current_user.id
    ).first()

    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    msg.feedback = body.feedback
    msg.feedback_comment = body.comment
    db.commit()

    logger.info(
        "Feedback received: msg_id=%s user_id=%s feedback=%s",
        message_id, current_user.id, body.feedback
    )
    # If negative feedback, log as failed query
    if body.feedback == "down":
        logger.warning(
            "NEGATIVE_FEEDBACK user_id=%s session_id=%s msg_id=%s comment=%r",
            current_user.id, msg.session_id, msg.id, body.comment
        )

    return {"status": "ok"}


@app.on_event("startup")
async def on_startup():
    init_db()
    logger.info("Database initialized")
