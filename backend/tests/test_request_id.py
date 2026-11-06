"""Day 7: every request gets a correlation ID, returned as X-Request-ID and stamped on its log lines."""
import asyncio
import logging
import re
from typing import Any, AsyncIterator, Dict, Iterator, List

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.core.logging import RequestIdFilter
from app.core.request_id import NO_REQUEST_ID, RequestIdMiddleware, current_request_id, incoming_request_id

LOGGER_NAME = "rag_assistant.test_request_id"
GENERATED_ID = re.compile(r"[0-9a-f]{32}")


class CaptureHandler(logging.Handler):
    """Collects records after RequestIdFilter ran, as the app's file and console handlers do."""

    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []
        self.addFilter(RequestIdFilter())

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _capture(logger_name: str) -> Iterator[CaptureHandler]:
    handler = CaptureHandler()
    log = logging.getLogger(logger_name)
    old_level = log.level
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    yield handler
    log.removeHandler(handler)
    log.setLevel(old_level)


@pytest.fixture
def captured() -> Iterator[CaptureHandler]:
    yield from _capture(LOGGER_NAME)


def build_app() -> FastAPI:
    app = FastAPI()
    log = logging.getLogger(LOGGER_NAME)

    @app.get("/sync")
    def sync_route() -> Dict[str, str]:  # sync: FastAPI runs it in the thread pool
        log.info("sync route")
        return {"id": current_request_id()}

    @app.get("/async")
    async def async_route(delay: float = 0.0) -> Dict[str, str]:
        await asyncio.sleep(delay)
        log.info("async route")
        return {"id": current_request_id()}

    @app.get("/stream")
    async def stream_route() -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            for i in range(3):
                await asyncio.sleep(0)
                log.info("event %d", i)
                yield f"data: {i}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    app.add_middleware(RequestIdMiddleware)
    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(build_app()) as test_client:
        yield test_client


def test_a_new_id_is_generated_returned_and_logged_from_a_sync_route(
    client: TestClient, captured: CaptureHandler
) -> None:
    response = client.get("/sync")

    request_id = response.headers["x-request-id"]
    assert GENERATED_ID.fullmatch(request_id)
    assert response.json() == {"id": request_id}
    assert [r.request_id for r in captured.records] == [request_id]


def test_each_request_gets_a_different_id(client: TestClient) -> None:
    ids = {client.get("/sync").headers["x-request-id"] for _ in range(3)}

    assert len(ids) == 3


def test_a_valid_client_id_is_kept(client: TestClient, captured: CaptureHandler) -> None:
    response = client.get("/sync", headers={"X-Request-ID": "frontend-42.retry_1"})

    assert response.headers["x-request-id"] == "frontend-42.retry_1"
    assert captured.records[0].request_id == "frontend-42.retry_1"


@pytest.mark.parametrize("unsafe", ["has space", "a" * 65, "semi;colon", "<script>", ""])
def test_an_unsafe_client_id_is_replaced(client: TestClient, unsafe: str) -> None:
    response = client.get("/sync", headers={"X-Request-ID": unsafe})

    assert GENERATED_ID.fullmatch(response.headers["x-request-id"])


def test_a_client_id_with_a_line_break_is_rejected() -> None:
    # HTTP clients refuse to send CR/LF in a header, so check the parser directly: echoed into
    # a log line, this would forge a second entry.
    forged = b"abc\r\n2026-11-07 - INFO - rag_assistant - [x] - admin logged in"

    assert incoming_request_id([(b"x-request-id", forged)]) is None
    assert incoming_request_id([(b"X-Request-ID", b"abc-123")]) == "abc-123"


def test_every_line_of_a_streamed_response_carries_the_id(
    client: TestClient, captured: CaptureHandler
) -> None:
    response = client.get("/stream")

    assert response.text == "data: 0\n\ndata: 1\n\ndata: 2\n\n"
    assert [r.request_id for r in captured.records] == [response.headers["x-request-id"]] * 3


def test_concurrent_requests_keep_their_own_ids(captured: CaptureHandler) -> None:
    app = build_app()

    async def run() -> List[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Different delays make the requests finish in a different order than they started.
            return await asyncio.gather(*(client.get("/async", params={"delay": d}) for d in (0.05, 0.0, 0.03, 0.01)))

    responses = asyncio.run(run())

    ids = [r.headers["x-request-id"] for r in responses]
    assert len(set(ids)) == 4
    assert [r.json()["id"] for r in responses] == ids
    assert sorted(r.request_id for r in captured.records) == sorted(ids)


def test_lines_logged_outside_a_request_get_a_dash(captured: CaptureHandler) -> None:
    logging.getLogger(LOGGER_NAME).info("startup")

    assert captured.records[0].request_id == NO_REQUEST_ID


def test_the_app_returns_the_id_and_logs_it_on_the_request_line(app: Any) -> None:
    capture = _capture("rag_assistant")
    handler = next(capture)
    try:
        with TestClient(app) as real_client:
            response = real_client.get("/health")
    finally:
        next(capture, None)

    request_id = response.headers["x-request-id"]
    assert response.status_code == 200
    assert GENERATED_ID.fullmatch(request_id)
    request_lines = [r for r in handler.records if r.getMessage().startswith("REQ GET /health")]
    assert [r.request_id for r in request_lines] == [request_id]
