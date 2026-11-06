import logging
import os
import re
from logging.handlers import RotatingFileHandler
from typing import Any

from app.core.request_id import current_request_id

# \w* also catches access_token=, id_token=, refresh_token=.
_TOKEN_PARAM = re.compile(r"(?i)\b\w*token=[^&\s\"']+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

TOKEN_REDACTED = "[token redacted]"
JWT_REDACTED = "[jwt redacted]"


def redact_secrets(text: str) -> str:
    # token= first: replacing the JWT first would leave a bare "token=" behind.
    return _JWT.sub(JWT_REDACTED, _TOKEN_PARAM.sub(TOKEN_REDACTED, text))


def _redact_arg(arg: Any) -> Any:
    return redact_secrets(arg) if isinstance(arg, str) else arg


class RedactSecretsFilter(logging.Filter):
    """Backstop for G8: scrubs bearer tokens from any record reaching a handler.

    Args are redacted one by one rather than merged into msg, because uvicorn's
    AccessFormatter unpacks record.args by position and would crash on an empty tuple.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # With args present, msg is a %-template; editing it could break the placeholders.
        if isinstance(record.msg, str) and not record.args:
            record.msg = redact_secrets(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_arg(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _redact_arg(v) for k, v in record.args.items()}

        # A secret split across msg and args ("token=%s", jwt) survives per-part redaction;
        # only then collapse to the formatted text. Never true for uvicorn access records,
        # whose path has already lost its query string.
        if record.args:
            formatted = record.getMessage()
            redacted = redact_secrets(formatted)
            if redacted != formatted:
                record.msg = redacted
                record.args = ()
        return True


class StripQueryStringFilter(logging.Filter):
    """uvicorn.access logs '%s - "%s %s HTTP/%s" %d' with the path + query as args[2]."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (args[0], args[1], args[2].split("?", 1)[0], args[3], args[4])
        return True


class RequestIdFilter(logging.Filter):
    """Stamps record.request_id for the formatter: the current request's ID, or "-" outside a
    request (startup, background work). On the handlers, so records propagated from child
    loggers ("rag_assistant.retrieval") get it too.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id()
        return True


def _add_filter_once(target: logging.Filterer, filter_type: type[logging.Filter]) -> None:
    if not any(isinstance(f, filter_type) for f in target.filters):
        target.addFilter(filter_type())


def install_log_redaction(app_logger: logging.Logger) -> None:
    # Handler-level filters see records propagated from child loggers too; logger-level
    # filters only see records created on that exact logger.
    access_logger = logging.getLogger("uvicorn.access")
    _add_filter_once(access_logger, StripQueryStringFilter)

    loggers = [app_logger, logging.getLogger(), logging.getLogger("uvicorn"), access_logger]
    for lg in loggers:
        for handler in lg.handlers:
            _add_filter_once(handler, RedactSecretsFilter)


_FILE_HANDLER_NAME = "rag_assistant.file"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("rag_assistant")

    # Idempotent: semantic_cache.py and main.py both call this, and a second set of handlers
    # wrote every line twice. Redaction is still (re)installed, because handlers added since
    # the first call (basicConfig's root handler, uvicorn's) need the filter too.
    if any(h.get_name() == _FILE_HANDLER_NAME for h in logger.handlers):
        install_log_redaction(logger)
        return logger

    if not os.path.exists("logs"):
        os.mkdir("logs")

    logger.setLevel(logging.INFO)
    # Our own console handler already prints these; propagating would repeat each line through
    # the root handler that basicConfig() installs at import time in three modules.
    logger.propagate = False

    handler = RotatingFileHandler("logs/app.log", maxBytes=5*1024*1024, backupCount=3)
    handler.set_name(_FILE_HANDLER_NAME)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - [%(request_id)s] - %(message)s'
    )
    handler.setFormatter(formatter)
    # The formatter needs record.request_id, so every handler using it must carry the filter.
    _add_filter_once(handler, RequestIdFilter)
    logger.addHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    _add_filter_once(console, RequestIdFilter)
    logger.addHandler(console)

    install_log_redaction(logger)
    return logger
