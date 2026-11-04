"""The conftest guard is what makes "no network" a checked property; prove it holds."""
import socket

import pytest
import redis
from google import genai

from tests.conftest import NetworkBlocked
from tests.fakes import FakeGenaiClient, FakeRedis


def test_internet_connection_is_refused() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(NetworkBlocked):
            sock.connect(("8.8.8.8", 443))


def test_dns_lookup_is_refused() -> None:
    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("generativelanguage.googleapis.com", 443)


@pytest.mark.parametrize("port", [6379, 6380])
def test_local_redis_ports_are_refused(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(NetworkBlocked):
            sock.connect(("127.0.0.1", port))


def test_every_redis_constructor_returns_the_fake() -> None:
    assert isinstance(redis.from_url("redis://localhost:6380/0"), FakeRedis)
    assert isinstance(redis.Redis(host="localhost", port=6380), FakeRedis)
    assert isinstance(redis.StrictRedis(host="localhost", port=6379), FakeRedis)


def test_gemini_client_is_the_fake() -> None:
    assert isinstance(genai.Client(api_key="anything"), FakeGenaiClient)
