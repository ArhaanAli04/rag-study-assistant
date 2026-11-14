"""Day 7: one Settings class replaces scattered os.getenv calls with identical defaults and
fallbacks. Each test pins one row of the before/after table in docs/briefs/day07.md.
"""
from pathlib import Path
from typing import Dict

import pytest
from pydantic import SecretStr, ValidationError

from app.core import config
from app.core.config import (
    DEFAULT_ALLOWED_ORIGINS,
    DEFAULT_GENERATION_MODEL,
    DEFAULT_REDIS_URL,
    DEFAULT_SEMANTIC_CACHE_REDIS_URL,
    Settings,
)

REQUIRED: Dict[str, str] = {
    "GEMINI_API_KEY": "gemini-key-value",
    "JWT_SECRET_KEY": "jwt-secret-value",
    "GOOGLE_CLIENT_ID": "client-id",
    "GOOGLE_CLIENT_SECRET": "google-secret-value",
    "GOOGLE_REDIRECT_URI": "http://testserver/auth/google/callback",
    "DATABASE_URL": "postgresql+psycopg://rag_app@localhost:5433/rag",
    "DATABASE_SCHEMA": "rag",
}
OPTIONAL = (
    "TAVILY_API_KEY", "JWT_ALGORITHM", "JWT_EXPIRATION_MINUTES", "REDIS_URL",
    "SEMANTIC_CACHE_REDIS_URL", "BASE_URL", "FRONTEND_URL", "ALLOWED_ORIGINS", "TESSERACT_PATH",
    "GEMINI_GENERATION_MODEL",
)


def load(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Settings from exactly these environment variables: no .env file, nothing inherited."""
    for name in (*REQUIRED, *OPTIONAL):
        monkeypatch.delenv(name, raising=False)
    for name, value in {**REQUIRED, **env}.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_defaults_when_only_required_variables_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    s = load(monkeypatch)

    assert s.TAVILY_API_KEY.get_secret_value() == ""
    assert (s.JWT_ALGORITHM, s.JWT_EXPIRATION_MINUTES) == ("HS256", 10080)
    assert s.redis_url == DEFAULT_REDIS_URL == "redis://localhost:6379/0"
    assert s.semantic_cache_redis_url == DEFAULT_SEMANTIC_CACHE_REDIS_URL == "redis://localhost:6379/1"
    assert (s.BASE_URL, s.FRONTEND_URL) == ("http://localhost:8000", "http://localhost:3000")
    assert s.allowed_origins == [
        "http://localhost:3000",
        "http://localhost:8000",
        "https://rag-study-assistant-chi.vercel.app",
    ]
    assert s.ALLOWED_ORIGINS == DEFAULT_ALLOWED_ORIGINS
    assert s.TESSERACT_PATH is None
    assert s.GEMINI_GENERATION_MODEL == DEFAULT_GENERATION_MODEL == "gemini-3.5-flash-lite"


def test_generation_model_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # B9: rolling back (or switching again) is an env var on Render, not a code change.
    assert load(monkeypatch, GEMINI_GENERATION_MODEL="gemini-2.5-flash-lite").GEMINI_GENERATION_MODEL == (
        "gemini-2.5-flash-lite"
    )


# T3 (Day 4): the semantic cache gets its own Redis DB without moving deployments that set
# only REDIS_URL. Moved here from test_semantic_cache.py on Day 7.

def test_dedicated_redis_url_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    s = load(monkeypatch, REDIS_URL="redis://redis:6379/0", SEMANTIC_CACHE_REDIS_URL="redis://redis:6379/1")

    assert s.semantic_cache_redis_url == "redis://redis:6379/1"
    assert s.redis_url == "redis://redis:6379/0"


def test_falls_back_to_shared_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    s = load(monkeypatch, REDIS_URL="redis://redis:6379/0")

    assert s.semantic_cache_redis_url == "redis://redis:6379/0"


def test_defaults_to_db_1_when_nothing_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    s = load(monkeypatch)

    assert s.semantic_cache_redis_url == DEFAULT_SEMANTIC_CACHE_REDIS_URL
    assert DEFAULT_SEMANTIC_CACHE_REDIS_URL.endswith("/1")


def test_empty_redis_values_behave_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    # The old code: os.getenv("REDIS_URL", default) kept "" as "", while the semantic cache's
    # `or` chain treated "" as unset. Both behaviours are kept as they were.
    s = load(monkeypatch, REDIS_URL="", SEMANTIC_CACHE_REDIS_URL="")

    assert s.redis_url == ""
    assert s.semantic_cache_redis_url == DEFAULT_SEMANTIC_CACHE_REDIS_URL

    s = load(monkeypatch, REDIS_URL="redis://redis:6379/0", SEMANTIC_CACHE_REDIS_URL="")
    assert s.semantic_cache_redis_url == "redis://redis:6379/0"


def test_allowed_origins_are_split_trimmed_and_empties_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    s = load(monkeypatch, ALLOWED_ORIGINS=" https://a.app , ,https://b.app,")

    assert s.allowed_origins == ["https://a.app", "https://b.app"]


def test_empty_allowed_origins_allows_no_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    assert load(monkeypatch, ALLOWED_ORIGINS="").allowed_origins == []


def test_empty_tavily_key_turns_web_search_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.retrieval.web.search_client import WebSearchClient

    monkeypatch.setattr(config.settings, "TAVILY_API_KEY", SecretStr(""))

    # retrieval_service catches this and answers without web chunks.
    with pytest.raises(RuntimeError, match="TAVILY_API_KEY not set"):
        WebSearchClient()


def test_empty_gemini_key_still_fails_when_a_client_is_built(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.gemini import build_gemini_client

    monkeypatch.setattr(config.settings, "GEMINI_API_KEY", SecretStr(""))

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY not set"):
        build_gemini_client()


def test_missing_required_variables_are_all_reported_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*REQUIRED, *OPTIONAL):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)

    missing = {error["loc"][0] for error in excinfo.value.errors()}
    assert missing == set(REQUIRED)


def test_secrets_never_appear_in_repr_or_str(monkeypatch: pytest.MonkeyPatch) -> None:
    s = load(monkeypatch, TAVILY_API_KEY="tavily-secret-value")

    rendered = repr(s) + str(s)
    for secret in ("gemini-key-value", "jwt-secret-value", "google-secret-value", "tavily-secret-value"):
        assert secret not in rendered
    assert s.GEMINI_API_KEY.get_secret_value() == "gemini-key-value"


def test_env_file_fills_gaps_and_real_environment_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("BASE_URL=http://from-env-file\nFRONTEND_URL=http://from-env-file\n", encoding="utf-8")
    load(monkeypatch, FRONTEND_URL="http://from-environment")

    s = Settings(_env_file=env_file)

    assert s.BASE_URL == "http://from-env-file"
    assert s.FRONTEND_URL == "http://from-environment"


# T2 (Day 13): one database URL with the driver and schema made explicit. Postgres only since Day 15.

@pytest.mark.parametrize("missing", ["DATABASE_URL", "DATABASE_SCHEMA"])
def test_database_url_and_schema_are_required(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    for name in (*REQUIRED, *OPTIONAL):
        monkeypatch.delenv(name, raising=False)
    for name, value in REQUIRED.items():
        if name != missing:
            monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=missing):
        Settings(_env_file=None)


def test_sqlite_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="must be a postgresql\\+psycopg:// URL"):
        load(monkeypatch, DATABASE_URL="sqlite:///data/app.db")


@pytest.mark.parametrize("prefix", ["postgresql", "postgres", "postgresql+psycopg2"])
def test_postgres_url_without_the_psycopg3_driver_is_refused(monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        load(monkeypatch, DATABASE_URL=f"{prefix}://rag_app:pw-secret@db.example:5432/postgres", DATABASE_SCHEMA="rag")

    message = str(excinfo.value)
    assert "postgresql+psycopg://" in message
    assert "pw-secret" not in message


def test_postgres_url_with_schema_is_accepted_and_stays_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    s = load(monkeypatch, DATABASE_URL="postgresql+psycopg://rag_app:pw-secret@localhost:5433/rag", DATABASE_SCHEMA="rag")

    assert s.database_scheme == "postgresql+psycopg"
    assert "pw-secret" not in repr(s) + str(s)


def test_unknown_database_scheme_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="must be a postgresql\\+psycopg:// URL"):
        load(monkeypatch, DATABASE_URL="mysql://u:p@localhost/db")


# Day 15: uploads in local storage by default; Supabase Storage needs its whole S3 configuration.

SUPABASE_STORAGE = {
    "STORAGE_BACKEND": "supabase",
    "STORAGE_BUCKET": "rag-staging",
    "SUPABASE_S3_ENDPOINT": "https://project-ref.storage.supabase.co/storage/v1/s3",
    "SUPABASE_S3_REGION": "ap-south-1",
    "SUPABASE_S3_ACCESS_KEY_ID": "access-key-id",
    "SUPABASE_S3_SECRET_ACCESS_KEY": "s3-secret-value",
}


def test_storage_is_local_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SUPABASE_STORAGE:
        monkeypatch.delenv(name, raising=False)

    assert load(monkeypatch).STORAGE_BACKEND == "local"


def test_supabase_storage_needs_every_s3_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SUPABASE_STORAGE:
        monkeypatch.delenv(name, raising=False)
    partial = {k: v for k, v in SUPABASE_STORAGE.items() if k != "SUPABASE_S3_SECRET_ACCESS_KEY"}

    with pytest.raises(ValidationError, match="SUPABASE_S3_SECRET_ACCESS_KEY"):
        load(monkeypatch, **partial)


def test_supabase_storage_secret_stays_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    s = load(monkeypatch, **SUPABASE_STORAGE)

    assert s.STORAGE_BACKEND == "supabase"
    assert "s3-secret-value" not in repr(s) + str(s)


def test_env_file_is_the_repo_root_dotenv_whatever_the_cwd() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    assert config.ENV_FILE == repo_root / ".env"
    assert config.ENV_FILE.is_absolute()
