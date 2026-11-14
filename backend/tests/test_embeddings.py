"""I3 (Day 16): embeddings go out in batches, uploads retry transient errors, the chat path doesn't."""
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, List

import httpx
import numpy as np
import pytest
from google.genai import errors as genai_errors

from app.retrieval.embeddings import (
    EMBED_BATCH_SIZE,
    EMBEDDING_DIM,
    MAX_RETRY_DELAY_SECONDS,
    EmbeddingError,
    EmbeddingService,
    server_retry_delay,
)
from tests.conftest import Account
from tests.fakes import FakeGemini


@dataclass
class _Vector:
    values: List[float]


@dataclass
class _Response:
    embeddings: List[_Vector]


@dataclass
class _ScriptedModels:
    """embed_content raises the queued errors first, then embeds: text i → a vector pointing at axis i."""

    errors: Deque[Exception] = field(default_factory=deque)
    batches: List[List[str]] = field(default_factory=list)
    short_by: int = 0

    def embed_content(self, model: str, contents: Any, config: Any = None) -> _Response:
        self.batches.append(list(contents))
        if self.errors:
            raise self.errors.popleft()
        vectors = []
        for text in contents[: len(contents) - self.short_by]:
            vector = [0.0] * EMBEDDING_DIM
            vector[int(text) % EMBEDDING_DIM] = 2.0  # not unit length: the service normalizes
            vectors.append(_Vector(vector))
        return _Response(vectors)


class _ScriptedClient:
    def __init__(self) -> None:
        self.models = _ScriptedModels()


def _service(max_attempts: int = 3) -> tuple[EmbeddingService, _ScriptedModels]:
    client = _ScriptedClient()
    return EmbeddingService(client, max_attempts=max_attempts), client.models  # type: ignore[arg-type]


def _rate_limited(retry_delay: str | None = None) -> genai_errors.ClientError:
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}] if retry_delay else []
    return genai_errors.ClientError(
        429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota", "details": details}}
    )


def test_no_texts_makes_no_call() -> None:
    service, models = _service()

    assert service.embed_texts([]).shape == (0, EMBEDDING_DIM)
    assert models.batches == []


def test_texts_are_sent_in_batches_and_come_back_in_input_order() -> None:
    service, models = _service()
    texts = [str(i) for i in range(2 * EMBED_BATCH_SIZE + 50)]

    vectors = service.embed_texts(texts)

    assert [len(b) for b in models.batches] == [EMBED_BATCH_SIZE, EMBED_BATCH_SIZE, 50]
    assert vectors.shape == (len(texts), EMBEDDING_DIM)
    assert [int(np.argmax(v)) for v in vectors] == list(range(len(texts)))
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)


def test_a_429_is_retried_after_the_servers_retry_delay(instant_embedding_backoff: List[float]) -> None:
    service, models = _service()
    models.errors.append(_rate_limited("37s"))

    vectors = service.embed_texts(["1", "2"])

    assert len(vectors) == 2
    assert len(models.batches) == 2
    assert instant_embedding_backoff == [37.0]


def test_the_servers_retry_delay_is_capped(instant_embedding_backoff: List[float]) -> None:
    service, models = _service()
    models.errors.append(_rate_limited("3600s"))

    service.embed_texts(["1"])

    assert instant_embedding_backoff == [MAX_RETRY_DELAY_SECONDS]


def test_without_a_hint_the_backoff_doubles(instant_embedding_backoff: List[float]) -> None:
    service, models = _service()
    models.errors.extend([genai_errors.ServerError(503, {"error": {"code": 503}}), httpx.ReadTimeout("slow")])

    service.embed_texts(["1"])

    first, second = instant_embedding_backoff
    assert 1.0 <= first <= 1.25 and 2.0 <= second <= 2.5


def test_a_bad_request_is_not_retried(instant_embedding_backoff: List[float]) -> None:
    service, models = _service()
    models.errors.append(genai_errors.ClientError(400, {"error": {"code": 400, "message": "empty text"}}))

    with pytest.raises(EmbeddingError, match="after 1 attempt"):
        service.embed_texts(["1"])
    assert instant_embedding_backoff == []


def test_it_gives_up_after_max_attempts(instant_embedding_backoff: List[float]) -> None:
    service, models = _service(max_attempts=3)
    models.errors.extend([_rate_limited(), _rate_limited(), _rate_limited()])

    with pytest.raises(EmbeddingError, match="batch 1 of 1 .* after 3 attempt"):
        service.embed_texts(["1"])
    assert len(instant_embedding_backoff) == 2


def test_the_chat_path_gets_one_attempt(instant_embedding_backoff: List[float]) -> None:
    service, models = _service(max_attempts=1)
    models.errors.append(_rate_limited("5s"))

    with pytest.raises(EmbeddingError):
        service.embed_texts(["1"])
    assert len(models.batches) == 1
    assert instant_embedding_backoff == []


def test_a_short_response_is_an_error_not_a_misaligned_index() -> None:
    service, models = _service()
    models.short_by = 1

    with pytest.raises(EmbeddingError, match="1 vectors for 2 texts"):
        service.embed_texts(["1", "2"])


def test_server_retry_delay_reads_only_retry_info() -> None:
    assert server_retry_delay(_rate_limited("12.5s")) == 12.5
    assert server_retry_delay(_rate_limited()) is None
    assert server_retry_delay(httpx.ReadTimeout("slow")) is None


def test_an_upload_survives_one_429(client: object, account: Account, gemini: FakeGemini) -> None:
    from tests.test_api_smoke import upload

    gemini.fail_embedding_at = 1

    response = upload(client, account)

    assert response.status_code == 200, response.text
    assert response.json()["chunks_indexed"] > 0
    assert gemini.embed_calls == 2  # the failed batch, then its retry
