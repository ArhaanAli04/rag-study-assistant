import logging
import random
import re
import time
from typing import Any, List

import httpx
import numpy as np
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

logger = logging.getLogger("rag_assistant.embeddings")

# Reused vectors (CO3, Day 16) are only valid for the model and size that made them: document_chunks
# stores no model name. Changing either invalidates every stored vector — it needs a migration (the
# column is halfvec(EMBEDDING_DIM)) and `python -m scripts.reindex_all --all --re-embed --apply`.
EMBEDDING_MODEL = "gemini-embedding-001"
# Requested on every call: gemini-embedding-001's default is 3072 (confirmed live, Day 9), and
# document_chunks.embedding is halfvec(3072) (Day 15, Decision 1B).
EMBEDDING_DIM = 3072

# batchEmbedContents (what embed_content sends for a list) accepts at most 100 inputs per request.
EMBED_BATCH_SIZE = 100
# Uploads retry (I3, Day 16): one 429 halfway through a lecture deck used to fail the whole upload.
# Chat-path embeddings get one attempt: they already degrade (keyword-only search, cache miss), and
# a chat turn embeds the question up to three times, so retries there would multiply an outage's wait.
INDEXING_MAX_ATTEMPTS = 3
QUERY_MAX_ATTEMPTS = 1
RETRY_BASE_DELAY_SECONDS = 1.0
# A 429 carries the server's retryDelay; the free tier's per-minute token budget (30K TPM, about one
# 100-chunk batch) refills within a minute, so the wait is honoured up to that and no longer: the
# upload request is held open meanwhile.
MAX_RETRY_DELAY_SECONDS = 60.0

_RETRY_DELAY = re.compile(r"^(\d+(?:\.\d+)?)s$")


class EmbeddingError(RuntimeError):
    """An embedding call failed. Raised instead of returning a zero vector: a zero vector has no
    direction, ranked first in hybrid search before B8, and document_chunks refuses it (Day 15)."""


def _sleep(seconds: float) -> None:
    # A module function, looked up at call time, so the test suite can make backoff instant.
    time.sleep(seconds)


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPError):  # timeouts and dropped connections
        return True
    if isinstance(error, genai_errors.ServerError):
        return True
    return isinstance(error, genai_errors.ClientError) and error.code == 429


def server_retry_delay(error: Exception) -> float | None:
    """The `retryDelay` a 429 carries in its google.rpc.RetryInfo detail ("37s"), if any."""
    if not isinstance(error, genai_errors.APIError) or not isinstance(error.details, dict):
        return None
    details: Any = error.details.get("error", {}).get("details", [])
    for detail in details if isinstance(details, list) else []:
        if isinstance(detail, dict) and str(detail.get("@type", "")).endswith("google.rpc.RetryInfo"):
            match = _RETRY_DELAY.match(str(detail.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    return None


class EmbeddingService:
    def __init__(
        self,
        client: genai.Client,
        model_name: str = EMBEDDING_MODEL,
        max_attempts: int = INDEXING_MAX_ATTEMPTS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.client = client
        self.model_name = model_name
        self.dimension = EMBEDDING_DIM
        self.max_attempts = max_attempts
        self._config = genai_types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """L2-normalized embeddings, shape (len(texts), EMBEDDING_DIM), in input order.

        Callers must not pass blank text: the API rejects it (400). Batches of EMBED_BATCH_SIZE are
        sent one after another (Day 16, Decision 1A); any batch that still fails after its attempts
        raises EmbeddingError, so the caller gets every vector or none.
        """
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

        batch_count = (len(texts) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE
        vectors: List[List[float]] = []
        for batch_number, start in enumerate(range(0, len(texts), EMBED_BATCH_SIZE), start=1):
            batch = texts[start:start + EMBED_BATCH_SIZE]
            where = f"batch {batch_number} of {batch_count} (texts {start + 1}-{start + len(batch)} of {len(texts)})"
            vectors.extend(self._embed_batch(batch, where))

        embeddings = np.array(vectors, dtype=np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise EmbeddingError("the API returned a zero vector")
        return embeddings / norms

    def _embed_batch(self, batch: List[str], where: str) -> List[List[float]]:
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self.client.models.embed_content(
                    model=self.model_name, contents=batch, config=self._config
                )
            except (genai_errors.APIError, httpx.HTTPError) as error:
                if attempt == self.max_attempts or not _is_retryable(error):
                    raise EmbeddingError(
                        f"embedding {where} failed after {attempt} attempt(s): {type(error).__name__}"
                    ) from error
                delay = self._retry_delay(error, attempt)
                logger.warning(
                    "Embedding %s: %s on attempt %d of %d, retrying in %.1f s",
                    where, type(error).__name__, attempt, self.max_attempts, delay,
                )
                _sleep(delay)
                continue
            embeddings = result.embeddings or []
            if len(embeddings) != len(batch):
                raise EmbeddingError(f"embedding {where}: {len(embeddings)} vectors for {len(batch)} texts")
            return [list(e.values or []) for e in embeddings]
        raise AssertionError("unreachable: the last attempt returns or raises")

    @staticmethod
    def _retry_delay(error: Exception, attempt: int) -> float:
        hinted = server_retry_delay(error)
        if hinted is not None:
            return min(hinted, MAX_RETRY_DELAY_SECONDS)
        backoff = RETRY_BASE_DELAY_SECONDS * 2 ** (attempt - 1)
        return backoff + random.uniform(0, backoff / 4)
