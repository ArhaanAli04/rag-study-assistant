"""G8: no log record may ever carry a bearer token."""
import logging
from pathlib import Path
from typing import Any, Iterator, Optional, Tuple

import pytest

from app.core.logging import (
    RedactSecretsFilter,
    StripQueryStringFilter,
    install_log_redaction,
    setup_logging,
)

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhQGIuY29tIn0.c2lnbmF0dXJl"
FORMATTER = logging.Formatter("%(name)s - %(message)s")


def _record(msg: str, args: Optional[Tuple[Any, ...]] = None, name: str = "rag_assistant") -> logging.LogRecord:
    return logging.LogRecord(name, logging.INFO, __file__, 1, msg, args, None)


def _through(record: logging.LogRecord, *filters: logging.Filter) -> str:
    for f in filters:
        assert f.filter(record) is True
    return FORMATTER.format(record)


def _assert_clean(output: str) -> None:
    assert "token=" not in output
    assert "eyJ" not in output


def test_token_in_args_is_redacted() -> None:
    out = _through(_record("GET %s", (f"/chat/stream?query=x&token={JWT}",)), RedactSecretsFilter())
    _assert_clean(out)
    assert "/chat/stream?query=x&" in out


def test_token_in_fstring_message_is_redacted() -> None:
    out = _through(_record(f"Redirecting to frontend: http://x/auth/callback?token={JWT}"), RedactSecretsFilter())
    _assert_clean(out)


def test_secret_split_across_msg_and_args_is_redacted() -> None:
    out = _through(_record("token=%s", (JWT,)), RedactSecretsFilter())
    _assert_clean(out)


def test_bare_jwt_is_redacted() -> None:
    out = _through(_record(f"Authorization: Bearer {JWT}"), RedactSecretsFilter())
    _assert_clean(out)


def test_access_token_param_is_redacted() -> None:
    out = _through(_record("callback?access_token=abc123&state=s"), RedactSecretsFilter())
    assert "abc123" not in out
    assert "state=s" in out


def test_ordinary_message_is_unchanged() -> None:
    out = _through(_record("REQ %s %s %d", ("GET", "/sessions", 200)), RedactSecretsFilter())
    assert out == "rag_assistant - REQ GET /sessions 200"


def test_uvicorn_access_record_loses_its_query_string() -> None:
    record = _record(
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", f"/chat/stream?query=hi&token={JWT}", "1.1", 200),
        name="uvicorn.access",
    )
    out = _through(record, StripQueryStringFilter(), RedactSecretsFilter())

    _assert_clean(out)
    assert out == 'uvicorn.access - 127.0.0.1:5000 - "GET /chat/stream HTTP/1.1" 200'
    # uvicorn's AccessFormatter unpacks exactly five positional args.
    assert isinstance(record.args, tuple) and len(record.args) == 5


@pytest.fixture
def isolated_logging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    watched = [logging.getLogger(n) for n in ("rag_assistant", "", "uvicorn", "uvicorn.access")]
    saved = [(lg, list(lg.handlers), list(lg.filters), lg.propagate) for lg in watched]
    # Other test modules import semantic_cache, which already ran setup_logging(); start each
    # test without those handlers so setup_logging() really configures from scratch.
    logging.getLogger("rag_assistant").handlers = []
    yield
    for lg, handlers, filters, propagate in saved:
        for h in lg.handlers:
            if h not in handlers:
                h.close()
        lg.handlers = handlers
        lg.filters = filters
        lg.propagate = propagate


@pytest.mark.usefixtures("isolated_logging")
def test_setup_logging_writes_no_token_to_app_log() -> None:
    logger = setup_logging()
    logger.info(f"Request: GET http://localhost:8000/chat/stream?query=hi&token={JWT}")
    for h in logger.handlers:
        h.flush()

    contents = Path("logs/app.log").read_text(encoding="utf-8")
    assert "/chat/stream" in contents
    _assert_clean(contents)


@pytest.mark.usefixtures("isolated_logging")
def test_setup_logging_twice_writes_each_line_once() -> None:
    # semantic_cache.py and main.py both call setup_logging(); each line used to appear twice.
    first = setup_logging()
    handlers_after_first = list(first.handlers)
    second = setup_logging()

    assert second is first
    assert second.handlers == handlers_after_first
    assert first.propagate is False  # the root handler would otherwise print it again
    second.info("exactly once")
    for h in second.handlers:
        h.flush()
    assert Path("logs/app.log").read_text(encoding="utf-8").count("exactly once") == 1


@pytest.mark.usefixtures("isolated_logging")
def test_second_setup_call_still_filters_handlers_added_since_the_first() -> None:
    # main.py's first setup_logging() runs (via semantic_cache) before concept_map_service's
    # basicConfig adds the root handler, so the second call must still install redaction.
    setup_logging()
    late_root_handler = logging.StreamHandler()
    logging.getLogger().addHandler(late_root_handler)

    setup_logging()

    assert any(isinstance(f, RedactSecretsFilter) for f in late_root_handler.filters)


@pytest.mark.usefixtures("isolated_logging")
def test_redaction_reaches_root_and_uvicorn_handlers() -> None:
    uvicorn_handler = logging.StreamHandler()
    root_handler = logging.StreamHandler()
    logging.getLogger("uvicorn.access").addHandler(uvicorn_handler)
    logging.getLogger().addHandler(root_handler)

    install_log_redaction(logging.getLogger("rag_assistant"))
    install_log_redaction(logging.getLogger("rag_assistant"))

    for handler in (uvicorn_handler, root_handler):
        assert sum(isinstance(f, RedactSecretsFilter) for f in handler.filters) == 1
    access_filters = logging.getLogger("uvicorn.access").filters
    assert sum(isinstance(f, StripQueryStringFilter) for f in access_filters) == 1
