"""Make the whole suite hermetic: no API keys, no network, no Redis, no files in the repo.

Everything here is installed in pytest_configure, before any test module is collected: the
engine is built from settings.DATABASE_URL at import, so the suite's own SQLite file must be set
first. Since Day 9 the app's
clients (Gemini, Redis) are built in the lifespan, which `with TestClient(app)` runs once per test,
so each test gets fresh indexes; the fakes still sit at the SDK constructors, which covers the
lifespan and the unit tests that build services directly alike.
"""
import ipaddress
import logging
import os
import shutil
import socket
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = BACKEND_DIR / "tests" / "samples"
# The container runs `pytest /app/backend/tests` without the repo's pytest.ini, so its
# `pythonpath = backend` doesn't apply there; backend/ must be on sys.path for `app` and `tests`.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.fakes import FakeGenaiClient, FakeGemini, FakeRedisServer, FakeTavilyClient  # noqa: E402

# Set before anything calls load_dotenv(): it never overrides an existing variable, so these win
# over the real root .env. The empty TAVILY_API_KEY keeps web search off (WebSearchClient refuses).
TEST_ENV = {
    "GEMINI_API_KEY": "test-gemini-key",
    "TAVILY_API_KEY": "",
    "JWT_SECRET_KEY": "test-jwt-secret-not-for-production",
    "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "GOOGLE_REDIRECT_URI": "http://testserver/auth/google/callback",
    "REDIS_URL": "redis://redis.invalid:6379/0",
    "SEMANTIC_CACHE_REDIS_URL": "redis://redis.invalid:6379/1",
}

# Local Docker Redis (6380) and a default local Redis (6379): a client that escapes the patches
# below must never reach real data.
BLOCKED_LOOPBACK_PORTS = {6379, 6380}


class NetworkBlocked(RuntimeError):
    """A test tried to open a real network connection."""


_state: Dict[str, Any] = {}
redis_server = FakeRedisServer()


def _is_loopback(host: str) -> bool:
    if host in ("localhost", "testserver"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guarded_connect(original: Any) -> Any:
    def connect(sock: socket.socket, address: Any) -> Any:
        # AF_INET / AF_INET6 addresses are tuples; anything else (AF_UNIX) is local by definition.
        if isinstance(address, tuple):
            host, port = str(address[0]), int(address[1])
            if not _is_loopback(host):
                raise NetworkBlocked(f"test tried to connect to {host}:{port}")
            if port in BLOCKED_LOOPBACK_PORTS:
                raise NetworkBlocked(f"test tried to reach a local Redis on port {port}")
        return original(sock, address)

    return connect


def _guarded_getaddrinfo(original: Any) -> Any:
    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> List[Tuple[Any, ...]]:
        if host is not None and not _is_loopback(host.decode() if isinstance(host, bytes) else str(host)):
            raise NetworkBlocked(f"test tried to resolve {host!r}")
        return original(host, *args, **kwargs)

    return getaddrinfo


def pytest_configure(config: pytest.Config) -> None:
    # data/, uploads/ and logs/ are resolved against the CWD at import time; keep them out of the repo.
    workdir = Path(tempfile.mkdtemp(prefix="rag-tests-"))
    # Since Day 13 the default database is an absolute path (backend/data/app.db, the developer's
    # real one), so the chdir below no longer isolates it: the suite gets its own SQLite file. Set
    # here, before settings is imported, and it also wins over a DATABASE_URL in the real .env.
    test_env = {**TEST_ENV, "DATABASE_URL": f"sqlite:///{(workdir / 'data' / 'app.db').as_posix()}"}
    for key, value in test_env.items():
        _state.setdefault("env", {})[key] = os.environ.get(key)
        os.environ[key] = value
    os.environ.pop("DATABASE_SCHEMA", None)

    import redis
    import tavily
    from google import genai

    _state["patched"] = [
        (tavily, "TavilyClient", tavily.TavilyClient),
        (redis, "from_url", redis.from_url),
        (redis, "Redis", redis.Redis),
        (redis, "StrictRedis", redis.StrictRedis),
        (genai, "Client", genai.Client),
        (socket.socket, "connect", socket.socket.connect),
        (socket.socket, "connect_ex", socket.socket.connect_ex),
        (socket, "getaddrinfo", socket.getaddrinfo),
    ]
    redis.from_url = redis_server.from_url
    redis.Redis = redis_server.client_class
    redis.StrictRedis = redis_server.client_class
    genai.Client = FakeGenaiClient
    tavily.TavilyClient = FakeTavilyClient  # web_search_client does `from tavily import TavilyClient` later
    socket.socket.connect = _guarded_connect(socket.socket.connect)
    socket.socket.connect_ex = _guarded_connect(socket.socket.connect_ex)
    socket.getaddrinfo = _guarded_getaddrinfo(socket.getaddrinfo)

    _state["cwd"] = os.getcwd()
    _state["workdir"] = workdir
    os.chdir(workdir)


def pytest_unconfigure(config: pytest.Config) -> None:
    if "cwd" not in _state:
        return
    os.chdir(_state["cwd"])
    # Windows can't delete open files: release the SQLite file and the app's log handlers first.
    db_module = sys.modules.get("app.db.session")
    if db_module is not None:
        db_module.engine.dispose()
    workdir = str(_state["workdir"])
    for name in ("rag_assistant", ""):
        log = logging.getLogger(name)
        for handler in list(log.handlers):
            if str(getattr(handler, "baseFilename", "")).startswith(workdir):
                handler.close()
                log.removeHandler(handler)
    for obj, name, original in reversed(_state["patched"]):
        setattr(obj, name, original)
    for key, old in _state["env"].items():
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old
    shutil.rmtree(_state["workdir"], ignore_errors=True)


@pytest.fixture
def gemini() -> Iterator[FakeGemini]:
    """Script Gemini for one test: queue `replies` / `streams`; inspect `prompts`."""
    FakeGenaiClient.gemini.reset()
    yield FakeGenaiClient.gemini
    FakeGenaiClient.gemini.reset()


@pytest.fixture
def web_search(monkeypatch: pytest.MonkeyPatch) -> Iterator[type]:
    """Turn web search on for one test; set FakeTavilyClient.results to what Tavily should return."""
    from pydantic import SecretStr

    from app.core.config import settings

    # The settings object is read once at import, so a later setenv would not reach it.
    monkeypatch.setattr(settings, "TAVILY_API_KEY", SecretStr("test-tavily-key"))
    FakeTavilyClient.results = []
    FakeTavilyClient.queries = []
    yield FakeTavilyClient
    FakeTavilyClient.results = []
    FakeTavilyClient.queries = []


@pytest.fixture(scope="session")
def app() -> Any:
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app: Any) -> Iterator[Any]:
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:  # `with` runs the startup event, which creates the tables
        yield test_client


class Account:
    def __init__(self, email: str, password: str, token: str) -> None:
        self.email = email
        self.password = password
        self.token = token

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def register_and_login(client: Any, email: Optional[str] = None, password: str = "correct-horse-1") -> Account:
    email = email or f"user-{uuid.uuid4().hex[:12]}@example.com"
    registered = client.post("/register", json={"email": email, "password": password})
    assert registered.status_code == 200, registered.text
    logged_in = client.post("/login", data={"username": email, "password": password})
    assert logged_in.status_code == 200, logged_in.text
    return Account(email, password, logged_in.json()["access_token"])


@pytest.fixture
def account(client: Any) -> Account:
    """A fresh user per test: per-user scoping is how the app isolates state, so it isolates tests too."""
    return register_and_login(client)
