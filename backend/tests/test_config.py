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
}
OPTIONAL = (
    "TAVILY_API_KEY", "JWT_ALGORITHM", "JWT_EXPIRATION_MINUTES", "REDIS_URL",
    "SEMANTIC_CACHE_REDIS_URL", "BASE_URL", "FRONTEND_URL", "ALLOWED_ORIGINS", "TESSERACT_PATH",
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


def test_env_file_is_the_repo_root_dotenv_whatever_the_cwd() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    assert config.ENV_FILE == repo_root / ".env"
    assert config.ENV_FILE.is_absolute()
