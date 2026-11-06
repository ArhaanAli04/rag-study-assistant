"""Every environment variable the backend reads: typed, validated once at import, in one place.

Precedence (pydantic-settings): real environment variables > the repo-root .env > defaults below.
Render and CI set real variables; locally the root .env fills in the rest.
"""
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute, because the CWD differs between uvicorn (backend/), pytest (repo root or a temp dir)
# and Docker (/app/backend). A missing file is skipped, which is what Docker and CI need.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

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
