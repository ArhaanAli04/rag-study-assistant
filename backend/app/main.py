"""App factory. `app = create_app()` below is what uvicorn serves (`uvicorn app.main:app`).

create_app() only configures — middleware, routers, handlers — so importing this module makes no
network calls and builds no clients. Everything long-lived is built in the lifespan, once per
server start (services/container.py).
"""
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import auth, chat, concepts, documents, feedback, health, quiz, sessions, users
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.request_id import RequestIdMiddleware
from app.db import models  # noqa: F401  (registers every table on Base.metadata for create_all)
from app.db.base import Base
from app.db.session import engine
from app.services.container import build_services

logger = setup_logging()

ROUTERS = (health, auth, users, documents, chat, sessions, feedback, quiz, concepts)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Until Alembic owns the schema (Day 13, Checkpoint 4): creates missing tables, alters nothing.
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")
    started = time.perf_counter()
    app.state.services = build_services()
    logger.info(f"Services built in {time.perf_counter() - started:.2f}s")
    try:
        yield
    finally:
        app.state.services.close()


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


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."}
    )


def create_app() -> FastAPI:
    app = FastAPI(title="RAG Study Assistant API", lifespan=lifespan)
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
    for router_module in ROUTERS:
        app.include_router(router_module.router)
    app.middleware("http")(log_requests)
    # Registered last on purpose: the last middleware added is the outermost, so the ID is already
    # set when log_requests and CORS run, and stays set for the whole SSE stream.
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(Exception, general_exception_handler)
    return app


app = create_app()
