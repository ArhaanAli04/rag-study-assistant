"""The engine and session factory, built once from settings.DATABASE_URL (T2, Day 13).

create_engine opens no connection, so importing this module (and app.main) stays network-free.
"""
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# The Supabase free tier's pooler caps client connections; one Render instance needs few.
POSTGRES_POOL_SIZE = 5
POSTGRES_MAX_OVERFLOW = 5
# Poolers and the free tier close idle connections. Recycling before that, and pinging on checkout,
# turns a dropped connection into a reconnect instead of a failed request after a quiet hour.
POSTGRES_POOL_RECYCLE_SECONDS = 300


def build_engine(url: str) -> Engine:
    """One engine per backend, configured for it explicitly. Also used by alembic/env.py."""
    backend = make_url(url).get_backend_name()
    if backend == "sqlite":
        database = make_url(url).database
        if database and database != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        # FastAPI runs sync dependencies and endpoints in a thread pool, so one connection is
        # used from several threads over a request; SQLite refuses that by default.
        return create_engine(url, connect_args={"check_same_thread": False})
    if backend == "postgresql":
        return create_engine(
            url,
            pool_pre_ping=True,
            pool_size=POSTGRES_POOL_SIZE,
            max_overflow=POSTGRES_MAX_OVERFLOW,
            pool_recycle=POSTGRES_POOL_RECYCLE_SECONDS,
        )
    raise ValueError(f"Unsupported database backend: {backend}")


engine = build_engine(settings.DATABASE_URL.get_secret_value())
SessionLocal = sessionmaker(bind=engine)
