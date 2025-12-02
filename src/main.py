from fastapi import FastAPI, File, UploadFile, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import os
from logger import setup_logging
from jose import JWTError, jwt

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



app = FastAPI()
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


class ChatResponse(BaseModel):
    answer: str
    session_id: int
    confidence: float
    fallback_used: bool
    grounding_level: Optional[str] = None  # NEW FIELD
    sources: List[Dict[str, Any]]


@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
async def register(email: str, password: str, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=email, hashed_password=get_password_hash(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email}

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

@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id_int = current_user.id
    user_id_str = str(current_user.id)
    doc_version = current_user.doc_version  # GET VERSION

    # 0) Semantic cache lookup
    cached = semantic_cache.lookup(body.query,user_doc_version=doc_version)
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
    recent_msgs_db = get_recent_messages(db, chat_session.id, limit=6)
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
    # 6) Build prompt + call LLM
    prompt = llm_client.build_prompt(
        question=body.query,
        context_chunks=compressed_context,
        recent_messages=recent_messages,
        grounding_level=grounding_level,
    )
    answer = llm_client.generate_answer(prompt)

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
    }

    # 8) Store in semantic cache
    semantic_cache.store(body.query, resp_dict, doc_version)

    return ChatResponse(**resp_dict)


@app.on_event("startup")
async def on_startup():
    init_db()
    logger.info("Database initialized")
