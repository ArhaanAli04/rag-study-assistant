"""The eval must never spend production's Gemini quota (owner's rule, Day 11).

The eval key comes from a separate Google Cloud project and is set as a real environment variable,
which overrides the repo-root .env (settings precedence). If the process key ends like the .env
key, the override didn't happen, so every live eval entry point refuses to start. Only the last
four characters are compared, and neither key is ever logged.
"""
from pathlib import Path

from app.core.config import ENV_FILE, settings

ENV_VAR = "GEMINI_API_KEY"


class ProductionKeyError(RuntimeError):
    pass


def dotenv_key(env_file: Path = ENV_FILE) -> str | None:
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() == ENV_VAR:
            return value.split(" #")[0].strip().strip("'\"") or None
    return None


def assert_eval_key(process_key: str | None = None, env_file: Path = ENV_FILE) -> None:
    key = process_key if process_key is not None else settings.GEMINI_API_KEY.get_secret_value()
    production = dotenv_key(env_file)
    if production is None:
        raise ProductionKeyError(f"cannot confirm the eval key: no {ENV_VAR} in {env_file}")
    if len(key) < 4 or key[-4:] == production[-4:]:
        raise ProductionKeyError(
            f"{ENV_VAR} is the production key from .env; set the eval project's key as an environment variable"
        )
