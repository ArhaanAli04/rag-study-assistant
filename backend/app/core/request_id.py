"""A correlation ID per HTTP request: set by RequestIdMiddleware, stamped on log lines by
app.core.logging.RequestIdFilter, returned to the client as X-Request-ID. Langfuse traces
(Day 23) carry the same ID so a trace can be joined to its log lines.
"""
import re
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = b"x-request-id"
NO_REQUEST_ID = "-"
# A client-supplied ID is written into every log line of its request: anything outside this
# alphabet could forge lines (CR/LF) or bloat them, so it is replaced, not escaped.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

# asyncio gives each task its own copy of the context, so concurrent requests never see each
# other's ID; Starlette carries it into the thread pool that runs sync endpoints.
request_id_var: ContextVar[str] = ContextVar("request_id", default=NO_REQUEST_ID)


def current_request_id() -> str:
    return request_id_var.get()


def incoming_request_id(headers: list[tuple[bytes, bytes]]) -> str | None:
    """The client's X-Request-ID if it is safe to log verbatim, else None."""
    for name, value in headers:
        if name.lower() == REQUEST_ID_HEADER:
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.fullmatch(candidate) else None
    return None


class RequestIdMiddleware:
    """Pure ASGI rather than BaseHTTPMiddleware, which re-wraps response bodies: /chat/stream is
    SSE, and the ID must stay set for the whole time the stream's generator runs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = incoming_request_id(scope.get("headers", [])) or uuid.uuid4().hex
        token = request_id_var.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != REQUEST_ID_HEADER]
                headers.append((REQUEST_ID_HEADER, request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)
