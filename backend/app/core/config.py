"""Every environment variable the backend reads: typed, validated once at import, in one place.

Precedence (pydantic-settings): real environment variables > the repo-root .env > defaults below.
Render and CI set real variables; locally the root .env fills in the rest.
"""
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute, because the CWD differs between uvicorn (backend/), pytest (repo root or a temp dir)
# and Docker (/app/backend). A missing file is skipped, which is what Docker and CI need.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
BACKEND_DIR = Path(__file__).resolve().parents[2]

POSTGRES_SCHEME = "postgresql+psycopg"

# B9 (Day 12): 3.5 Flash-Lite allows 500 requests a day on the free tier (2.5 Flash-Lite: 20) and passed
# the generation eval's absolute gate. Set GEMINI_GENERATION_MODEL to override (or roll back) without a deploy.
DEFAULT_GENERATION_MODEL = "gemini-3.5-flash-lite"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_SEMANTIC_CACHE_REDIS_URL = "redis://localhost:6379/1"
DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000,http://localhost:8000,https://rag-study-assistant-chi.vercel.app"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # SecretStr: repr(settings), tracebacks and log lines show ********** instead of the key;
    # reading the value takes an explicit, greppable .get_secret_value().
    GEMINI_API_KEY: SecretStr
    # The answer, topic-tag and concept-map model (B9): one setting so a quota or quality change
    # is an env var on Render, not a code change in three classes.
    GEMINI_GENERATION_MODEL: str = DEFAULT_GENERATION_MODEL
    # Empty means web search is off: WebSearchClient refuses and retrieval skips web chunks.
    TAVILY_API_KEY: SecretStr = SecretStr("")

    JWT_SECRET_KEY: SecretStr
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60 * 24 * 7

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: SecretStr
    GOOGLE_REDIRECT_URI: str

    # Optional rather than defaulted: the semantic cache falls back to REDIS_URL only when it is
    # actually set, so "unset" must stay distinguishable from "set to the default".
    REDIS_URL: str | None = None
    SEMANTIC_CACHE_REDIS_URL: str | None = None

    BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    # A comma-separated string, not list[str]: pydantic-settings parses list fields as JSON.
    ALLOWED_ORIGINS: str = DEFAULT_ALLOWED_ORIGINS

    # Windows installs tesseract outside PATH, so the host .env points at the .exe. Unset,
    # pytesseract finds `tesseract` on PATH; the Docker image sets /usr/bin/tesseract anyway.
    TESSERACT_PATH: str | None = None

    # Postgres only since Day 15 (document_chunks needs pgvector and full-text search), so there is
    # no default: a missing URL fails startup instead of silently opening some local file.
    # A Postgres URL carries the role's password, so it is a secret like the API keys.
    DATABASE_URL: SecretStr
    # The schema the Postgres role's search_path must resolve to (rag, rag_staging). Models are
    # schema-agnostic; this only lets Alembic and the app refuse a role whose search_path was lost,
    # which would otherwise create every table in `public`.
    DATABASE_SCHEMA: str

    # Where uploaded files live (Day 15). "local": the uploads/ directory under the backend's working
    # directory (dev, tests, Docker volume). "supabase": a private Supabase Storage bucket over its S3
    # API (Render: its disk is wiped on every restart). S3 access keys reach Storage only, not the
    # database or Auth (Decision 5B).
    STORAGE_BACKEND: Literal["local", "supabase"] = "local"
    STORAGE_BUCKET: str | None = None
    SUPABASE_S3_ENDPOINT: str | None = None
    SUPABASE_S3_REGION: str | None = None
    SUPABASE_S3_ACCESS_KEY_ID: str | None = None
    SUPABASE_S3_SECRET_ACCESS_KEY: SecretStr | None = None

    @model_validator(mode="after")
    def _check_storage_settings(self) -> "Settings":
        if self.STORAGE_BACKEND != "supabase":
            return self
        missing = [
            name
            for name in (
                "STORAGE_BUCKET", "SUPABASE_S3_ENDPOINT", "SUPABASE_S3_REGION",
                "SUPABASE_S3_ACCESS_KEY_ID", "SUPABASE_S3_SECRET_ACCESS_KEY",
            )
            if not getattr(self, name)
        ]
        if missing:
            raise ValueError(f"STORAGE_BACKEND=supabase also needs: {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def _check_database_settings(self) -> "Settings":
        # Messages never echo the URL: it may hold a password.
        scheme = self.database_scheme
        if scheme in ("postgres", "postgresql") or (scheme.startswith("postgresql+") and scheme != POSTGRES_SCHEME):
            raise ValueError(
                f"DATABASE_URL must start with {POSTGRES_SCHEME}:// (the installed psycopg 3 driver); "
                f"got {scheme}://. Replace the prefix of the URL Supabase gives you."
            )
        if scheme != POSTGRES_SCHEME:
            raise ValueError(f"DATABASE_URL must be a {POSTGRES_SCHEME}:// URL; got {scheme}://")
        return self

    @property
    def database_scheme(self) -> str:
        return self.DATABASE_URL.get_secret_value().split("://", 1)[0].lower()

    @property
    def redis_url(self) -> str:
        """Query and web caches. Set-but-empty stays empty, as os.getenv(name, default) did."""
        return DEFAULT_REDIS_URL if self.REDIS_URL is None else self.REDIS_URL

    @property
    def semantic_cache_redis_url(self) -> str:
        # A dedicated setting lets the semantic cache live in its own Redis DB, so flushing the
        # query/web caches in REDIS_URL's DB doesn't wipe it. Falling back to REDIS_URL keeps
        # deployments that set only REDIS_URL (Render today) on their current DB.
        return self.SEMANTIC_CACHE_REDIS_URL or self.REDIS_URL or DEFAULT_SEMANTIC_CACHE_REDIS_URL

    @property
    def allowed_origins(self) -> list[str]:
        # Explicit allowlist: with "*" and credentials, Starlette echoes back any Origin that
        # sends a cookie (G4). Stripped, because "https://x.app " would never match an Origin.
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()
