import logging
from typing import List

import httpx
import numpy as np
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

logger = logging.getLogger("rag_assistant.embeddings")

EMBEDDING_MODEL = "gemini-embedding-001"
# Requested on every call: gemini-embedding-001's default is 3072 (confirmed live, Day 9), and
# document_chunks.embedding is halfvec(3072) (Day 15, Decision 1B). Changing it invalidates every
# stored vector and needs a migration plus a reindex.
EMBEDDING_DIM = 3072


class EmbeddingError(RuntimeError):
    """An embedding call failed. Raised instead of returning a zero vector: a zero vector has no
    direction, ranked first in hybrid search before B8, and document_chunks refuses it (Day 15)."""


class EmbeddingService:
    def __init__(self, client: genai.Client, model_name: str = EMBEDDING_MODEL) -> None:
        self.client = client
        self.model_name = model_name
        self.dimension = EMBEDDING_DIM
        self._config = genai_types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """L2-normalized embeddings, shape (len(texts), EMBEDDING_DIM).

        Callers must not pass blank text: the API rejects it (400). One call per text (I3, Day 16).
        """
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

        embeddings_list = []
        for position, text in enumerate(texts):
            try:
                result = self.client.models.embed_content(
                    model=self.model_name,
                    contents=text,
                    config=self._config,
                )
            except (genai_errors.APIError, httpx.HTTPError) as error:
                raise EmbeddingError(
                    f"embedding text {position + 1} of {len(texts)} failed: {type(error).__name__}"
                ) from error
            embeddings_list.append(result.embeddings[0].values)

        embeddings = np.array(embeddings_list, dtype=np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise EmbeddingError("the API returned a zero vector")
        return embeddings / norms
