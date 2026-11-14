"""T2 (Day 13): Alembic is the only path to the schema, and its migrations match the models.

Day 15: on the suite's own Postgres _test database (SQLite can't hold document_chunks). Tests that
downgrade it always finish by upgrading back to head, so every other test still finds a migrated
database; conftest's downgrade base + upgrade head runs the whole path once more before each run.
"""
from typing import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base
from app.db.migrations import SchemaNotAtHead, alembic_config, assert_schema_at_head, head_revision
from app.db.session import engine


@pytest.fixture
def at_head_afterwards() -> Iterator[None]:
    yield
    command.upgrade(alembic_config(), "head")


def test_there_is_exactly_one_head() -> None:
    # Two heads means two branches of history; `upgrade head` would refuse to choose.
    assert len(ScriptDirectory.from_config(alembic_config()).get_heads()) == 1


def test_upgrade_head_creates_every_model_table() -> None:
    tables = set(inspect(engine).get_table_names())

    assert tables == set(Base.metadata.tables) | {"alembic_version"}
    # The concept-map tables were the ones T2's old env.py would have dropped.
    assert {"concept_maps", "concept_map_nodes", "document_chunks"} <= tables


def test_migrated_schema_has_no_diff_against_the_models() -> None:
    with engine.connect() as connection:
        connection.dialect.ischema_names["halfvec"] = HALFVEC
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_constraints_carry_the_naming_convention() -> None:
    inspector = inspect(engine)

    assert {fk["name"] for fk in inspector.get_foreign_keys("messages")} == {
        "fk_messages_session_id_sessions",
        "fk_messages_user_id_users",
    }
    assert [uq["name"] for uq in inspector.get_unique_constraints("users")] == ["uq_users_email"]


def _delete_rules() -> dict[str, str]:
    """{constraint name: pg_constraint.confdeltype} for every FK: a = no action, c = cascade, n = set null."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select conname, confdeltype from pg_constraint "
                "where contype = 'f' and connamespace = current_schema()::regnamespace"
            )
        )
        return {name: rule for name, rule in rows}


def test_user_foreign_keys_cascade_and_failed_queries_detach_from_sessions() -> None:
    rules = _delete_rules()

    for table in ("sessions", "documents", "messages", "failed_queries", "concept_maps", "document_chunks"):
        assert rules[f"fk_{table}_user_id_users"] == "c", table
    assert rules["fk_document_chunks_document_id_documents"] == "c"
    assert rules["fk_concept_map_nodes_map_id_concept_maps"] == "c"
    assert rules["fk_failed_queries_session_id_sessions"] == "n"
    # Unchanged on purpose: messages go with their session in code (sessions_repo), not by the schema.
    assert rules["fk_messages_session_id_sessions"] == "a"


def test_chunk_search_indexes_exist() -> None:
    with engine.connect() as connection:
        definitions = dict(
            connection.execute(
                text("select indexname, indexdef from pg_indexes where tablename = 'document_chunks'")
            ).all()
        )

    assert "USING hnsw (embedding halfvec_cosine_ops)" in definitions["ix_document_chunks_embedding_hnsw"]
    assert "USING gin (tsv)" in definitions["ix_document_chunks_tsv"]
    assert "(user_id, document_id)" in definitions["ix_document_chunks_user_id_document_id"]


@pytest.mark.parametrize(
    ("chunk_text", "embedding", "constraint"),
    [
        ("real text", "[" + ",".join(["0"] * 3072) + "]", "ck_document_chunks_embedding_not_zero"),
        ("   ", "[" + ",".join(["1"] + ["0"] * 3071) + "]", "ck_document_chunks_text_not_blank"),
    ],
)
def test_database_refuses_zero_vectors_and_blank_chunks(chunk_text: str, embedding: str, constraint: str) -> None:
    # EmbeddingService used to store a zero vector when a call failed; the schema now refuses one.
    with engine.connect() as connection, connection.begin() as transaction:
        user_id = connection.execute(
            text("insert into users (email) values (:email) returning id"), {"email": f"ck-{constraint}@example.com"}
        ).scalar_one()
        document_id = connection.execute(
            text(
                "insert into documents (user_id, file_name, file_path, file_hash) "
                "values (:u, 'a.pdf', 'k', 'h') returning id"
            ),
            {"u": user_id},
        ).scalar_one()
        with pytest.raises(IntegrityError, match=constraint):
            connection.execute(
                text(
                    "insert into document_chunks (user_id, document_id, document_version, chunk_index, text, "
                    "content_hash, embedding, metadata, created_at) "
                    "values (:u, :d, 1, 0, :t, 'x', cast(:e as halfvec), '{}', now())"
                ),
                {"u": user_id, "d": document_id, "t": chunk_text, "e": embedding},
            )
        transaction.rollback()


def test_downgrade_base_removes_every_table(at_head_afterwards: None) -> None:
    command.downgrade(alembic_config(), "base")

    assert set(inspect(engine).get_table_names()) == {"alembic_version"}


def test_app_refuses_an_unmigrated_database(at_head_afterwards: None) -> None:
    command.downgrade(alembic_config(), "base")

    with pytest.raises(SchemaNotAtHead, match="alembic upgrade head"):
        assert_schema_at_head(engine)


def test_app_accepts_a_database_at_head() -> None:
    assert_schema_at_head(engine)
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"version_table_schema": connection.execute(text("select current_schema()")).scalar()}
        )
        assert context.get_current_revision() == head_revision()
