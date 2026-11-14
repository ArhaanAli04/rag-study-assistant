"""The engine and session factory, built once from settings.DATABASE_URL (T2, Day 13).

Postgres only since Day 15: document_chunks uses pgvector and full-text search.
create_engine opens no connection, so importing this module (and app.main) stays network-free.
"""
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
    """The app's engine configuration. Also used by alembic/env.py and the eval."""
    backend = make_url(url).get_backend_name()
    if backend != "postgresql":
        raise ValueError(f"Unsupported database backend: {backend}")
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=POSTGRES_POOL_SIZE,
        max_overflow=POSTGRES_MAX_OVERFLOW,
        pool_recycle=POSTGRES_POOL_RECYCLE_SECONDS,
    )


engine = build_engine(settings.DATABASE_URL.get_secret_value())
SessionLocal = sessionmaker(bind=engine)
