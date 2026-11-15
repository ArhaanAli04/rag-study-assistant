"""backend/scripts/measure_latency.py (Day 17): one connection for the whole run, token never logged.

A real local HTTP/1.1 server, not httpx.MockTransport: the bug was a connection that wasn't reused,
and a mock transport has no connections. Day 17's first local run stopped reading each chat stream
at [DONE], so httpx closed the connection and every later turn paid for a new one (~2 s on Windows'
localhost, a TLS handshake on Render), inflating every chat number after the first.
"""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator, List, Tuple

import pytest

from scripts.measure_latency import TOKEN_ENV, main, measure

TOKEN = "secret-test-token-abc"


class _CountingHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive, like uvicorn
    connections = 0
    paths: List[str] = []

    def setup(self) -> None:
        type(self).connections += 1  # one handler instance per TCP connection
        super().setup()

    def log_message(self, format: str, *args: Any) -> None:
        pass  # keep the test output clean

    def _send(self, body: bytes, content_type: str, extra: Tuple[Tuple[str, str], ...] = ()) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        type(self).paths.append(self.path.split("?", 1)[0])
        if self.path.startswith("/chat/stream"):
            frames = [
                {"type": "metadata", "data": {"session_id": 7, "sources": []}},
                {"type": "token", "data": "An answer."},
                {"type": "message_id", "data": 1},
            ]
            body = "".join(f"data: {json.dumps(f)}\n\n" for f in frames) + "data: [DONE]\n\n"
            # Bytes after [DONE] are what the old early `break` left unread; real streams can end
            # with trailing whitespace or a closing chunk too.
            self._send((body + "\n").encode(), "text/event-stream")
        else:
            self._send(b'{"ok": true}', "application/json")


@pytest.fixture
def server() -> Iterator[str]:
    _CountingHandler.connections = 0
    _CountingHandler.paths = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _CountingHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_one_connection_serves_the_warmup_health_me_and_every_chat_turn(server: str) -> None:
    results = measure(server, TOKEN, n_light=2, n_chat=2)

    # warm-up (/health, /me, chat) + 2 x /health + 2 x /me + 2 chat turns
    assert _CountingHandler.paths.count("/chat/stream") == 3
    assert _CountingHandler.connections == 1
    assert [c.problem for c in results.chats] == [None, None]
    assert all(c.to_metadata_ms is not None and c.total_ms is not None for c in results.chats)


def test_the_token_is_never_logged(
    server: str, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Through main(), the real entry point: it is what silences httpx, which logs every request URL
    # (and a chat URL carries ?token=) at INFO. Everything else is captured down to DEBUG.
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv(TOKEN_ENV, TOKEN)

    assert main(["--base-url", server, "--n", "1", "--chat", "1"]) == 0

    assert "chat -> metadata (n = 1)" in caplog.text
    assert TOKEN not in caplog.text
