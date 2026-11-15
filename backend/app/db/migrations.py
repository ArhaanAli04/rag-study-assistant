"""Alembic as the app sees it (T2, Day 13): where the scripts live, which revision is head, and
whether a database is there. Migrations themselves run as their own step (`alembic upgrade head`,
before uvicorn in Docker), never from the app; the app only refuses to start on a stale schema.
"""
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, text

from app.core.config import BACKEND_DIR, settings

# alembic.ini sits at the repo root: /app/alembic.ini in the image, next to /app/backend.
ALEMBIC_INI = BACKEND_DIR.parent / "alembic.ini"


class SchemaNotAtHead(RuntimeError):
    """The database's Alembic revision differs from the code's head revision."""


class WrongSchema(RuntimeError):
    """The Postgres role's search_path doesn't resolve to DATABASE_SCHEMA."""


def alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    # env.py would otherwise call logging.config.fileConfig and replace the app's (or pytest's)
    # logging setup with alembic.ini's.
    config.attributes["configure_logger"] = False
    return config


def version_table_schema() -> str:
    """Where alembic_version lives: inside the environment's own schema."""
    return settings.DATABASE_SCHEMA


def assert_expected_schema(connection: Connection) -> None:
    """Refuse a connection whose unqualified names would land outside DATABASE_SCHEMA.

    The schema comes from the role's search_path, not the URL. If that setting is lost, CREATE
    TABLE goes to `public` silently; this turns it into an error before anything is written.
    """
    current = connection.execute(text("select current_schema()")).scalar()
    if current != settings.DATABASE_SCHEMA:
        raise WrongSchema(
            f"Connected role resolves to schema {current!r}, expected DATABASE_SCHEMA={settings.DATABASE_SCHEMA!r}. "
            "Check the role's search_path (ALTER ROLE ... SET search_path)."
        )


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(connection: Connection) -> str | None:
    context = MigrationContext.configure(
        connection, opts={"version_table_schema": version_table_schema()}
    )
    return context.get_current_revision()


def assert_schema_at_head(engine: Engine) -> None:
    """Fail fast at startup instead of with a missing-column error in a user's request."""
    head = head_revision()
    with engine.connect() as connection:
        assert_expected_schema(connection)
        current = current_revision(connection)
    if current != head:
        raise SchemaNotAtHead(
            f"Database schema is at {current or 'no revision'}, the code expects {head}. "
            "Run `alembic upgrade head` from the repo root (Docker runs it before uvicorn starts)."
        )
