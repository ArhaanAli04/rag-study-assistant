"""Alembic environment (T2, Day 13): the app's own URL, models and engine settings.

Run from the repo root (`alembic upgrade head`); alembic.ini puts backend/ on sys.path.
- URL: app.core.config.settings.DATABASE_URL, the same one the app uses. Nothing in alembic.ini.
- Models: app.db.models imports every table, so autogenerate never mistakes one for deleted.
- Postgres only (Day 15): alembic_version lives inside DATABASE_SCHEMA, and a connection whose
  search_path resolves elsewhere is refused before anything runs (assert_expected_schema).
- pgvector's halfvec is registered for reflection, so autogenerate compares it as a type instead of
  reporting the column as an unknown type on every `alembic check`.
- Tests pass their own connection in config.attributes["connection"].
"""
from logging.config import fileConfig
from typing import Any, Dict

from alembic import context
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import Connection

from app.core.config import settings
from app.db import models  # noqa: F401  (registers every table, concept maps included)
from app.db.base import Base
from app.db.migrations import assert_expected_schema, version_table_schema
from app.db.session import build_engine

config = context.config

# The CLI configures logging from alembic.ini; the app and tests set configure_logger=False so
# their own logging setup survives an in-process upgrade.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def include_name(name: str | None, type_: str, parent_names: Dict[str, Any]) -> bool:
    # alembic_version is created as DATABASE_SCHEMA.alembic_version, but autogenerate compares the
    # default (unqualified) schema, where search_path shows the same table again; without this it
    # is reported as a removed model and the revision gets op.drop_table('alembic_version').
    return not (type_ == "table" and name == "alembic_version")


def configure_options() -> Dict[str, Any]:
    return {
        "target_metadata": target_metadata,
        "include_name": include_name,
        "compare_type": True,
        "version_table_schema": version_table_schema(),
    }


def run_migrations_offline() -> None:
    """Emit SQL to stdout (`alembic upgrade head --sql`) without connecting."""
    context.configure(
        url=settings.DATABASE_URL.get_secret_value(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **configure_options(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_on(connection: Connection) -> None:
    assert_expected_schema(connection)
    connection.dialect.ischema_names["halfvec"] = HALFVEC
    context.configure(connection=connection, **configure_options())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        run_on(connection)
        return
    engine = build_engine(settings.DATABASE_URL.get_secret_value())
    try:
        # begin(), not connect(): the schema guard's SELECT autobegins a transaction, and Alembic's
        # begin_transaction() then defers to it instead of committing. With connect() the whole
        # upgrade ran and was rolled back on close; begin() commits it (or rolls back on error).
        with engine.begin() as connection:
            run_on(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
