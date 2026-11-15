"""The eval's own Postgres database (Day 15, Decision 3A).

Retrieval runs in Postgres since Day 15, so the eval indexes its corpus into a database too: a
dedicated one, named *_eval, never dev or the suite's *_test. The name check is the guard: the
eval deletes and re-creates its corpus user there on every run.

Set EVAL_DATABASE_URL (postgresql+psycopg://rag_app:…@localhost:5433/rag_eval locally). The role's
search_path must resolve to the same schema as DATABASE_SCHEMA (rag), as the init script sets up.
"""
import os

from alembic import command
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.migrations import alembic_config
from app.db.session import build_engine

EVAL_DATABASE_SUFFIX = "_eval"


class EvalDatabaseError(RuntimeError):
    pass


def eval_session_factory() -> sessionmaker:
    """A session factory on EVAL_DATABASE_URL, migrated to head (idempotent)."""
    url = os.environ.get("EVAL_DATABASE_URL")
    if not url:
        raise EvalDatabaseError(
            "EVAL_DATABASE_URL is not set. The eval indexes its corpus into Postgres since Day 15: point it "
            "at the compose Postgres's rag_eval database (CLAUDE.md, Key Commands)."
        )
    parsed = make_url(url)
    # Never echo the URL: it may carry a password.
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith(EVAL_DATABASE_SUFFIX):
        raise EvalDatabaseError(
            f"EVAL_DATABASE_URL must be a postgresql+psycopg:// URL whose database name ends in {EVAL_DATABASE_SUFFIX}."
        )
    engine = build_engine(url)
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return sessionmaker(bind=engine)
