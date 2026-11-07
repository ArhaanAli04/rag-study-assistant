import time
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import auth, chat, concepts, documents, feedback, health, quiz, sessions, users
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.request_id import RequestIdMiddleware
from app.db.database import init_db
from app.services.container import build_services

logger = setup_logging()

app = FastAPI(title="RAG Study Assistant API")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.JWT_SECRET_KEY.get_secret_value()
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers
)

for router_module in (health, auth, users, documents, chat, sessions, feedback, quiz, concepts):
    app.include_router(router_module.router)

app.state.services = build_services()


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
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."}
    )


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    logger.info("Database initialized")
