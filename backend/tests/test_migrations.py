"""T2 (Day 13): Alembic is the only path to the schema, and its baseline matches the models.

These run on their own temporary SQLite files on purpose (downgrade round trips, a database at no
revision), whatever database the rest of the suite uses. CI also runs `alembic upgrade head` plus
`alembic check` against its Postgres service, and conftest's downgrade base + upgrade head runs on it
before every Postgres test run, so the baseline is proven on both dialects.
"""
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect

from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base
from app.db.migrations import SchemaNotAtHead, alembic_config, assert_schema_at_head, head_revision


@pytest.fixture
def empty_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_engine(f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}")
    yield engine
    engine.dispose()


def run_alembic(engine: Engine, action: str, revision: str) -> None:
    """Run an Alembic command on this engine's database, not the one settings points at."""
    config: Config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        getattr(command, action)(config, revision)


def test_there_is_exactly_one_head() -> None:
    # Two heads means two branches of history; `upgrade head` would refuse to choose.
    assert len(ScriptDirectory.from_config(alembic_config()).get_heads()) == 1


def test_upgrade_head_on_an_empty_database_creates_every_model_table(empty_engine: Engine) -> None:
    run_alembic(empty_engine, "upgrade", "head")

    tables = set(inspect(empty_engine).get_table_names())
    assert tables == set(Base.metadata.tables) | {"alembic_version"}
    # The concept-map tables were the ones T2's old env.py would have dropped.
    assert {"concept_maps", "concept_map_nodes"} <= tables


def test_migrated_schema_has_no_diff_against_the_models(empty_engine: Engine) -> None:
    run_alembic(empty_engine, "upgrade", "head")

    with empty_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_constraints_carry_the_naming_convention(empty_engine: Engine) -> None:
    run_alembic(empty_engine, "upgrade", "head")
    inspector = inspect(empty_engine)

    assert {fk["name"] for fk in inspector.get_foreign_keys("messages")} == {
        "fk_messages_session_id_sessions",
        "fk_messages_user_id_users",
    }
    assert [uq["name"] for uq in inspector.get_unique_constraints("users")] == ["uq_users_email"]


def test_downgrade_base_removes_every_table(empty_engine: Engine) -> None:
    run_alembic(empty_engine, "upgrade", "head")
    run_alembic(empty_engine, "downgrade", "base")

    assert set(inspect(empty_engine).get_table_names()) == {"alembic_version"}


def test_app_refuses_an_unmigrated_database(empty_engine: Engine) -> None:
    with pytest.raises(SchemaNotAtHead, match="alembic upgrade head"):
        assert_schema_at_head(empty_engine)


def test_app_accepts_a_database_at_head(empty_engine: Engine) -> None:
    run_alembic(empty_engine, "upgrade", "head")

    assert_schema_at_head(empty_engine)
    with empty_engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == head_revision()
