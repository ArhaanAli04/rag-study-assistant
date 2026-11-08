import logging
from typing import List

import numpy as np
from google import genai
from google.genai import types as genai_types

logger = logging.getLogger("rag_assistant.embeddings")

EMBEDDING_MODEL = "gemini-embedding-001"
# Requested on every call so the FAISS index can be sized without a startup probe call.
# gemini-embedding-001's default is 3072 (confirmed live, Day 9); changing it invalidates
# every stored vector.
EMBEDDING_DIM = 3072


class EmbeddingService:
    def __init__(self, client: genai.Client, model_name: str = EMBEDDING_MODEL) -> None:
        self.client = client
        self.model_name = model_name
        self.dimension = EMBEDDING_DIM
        self._config = genai_types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        Returns a 2D numpy array of shape (len(texts), embedding_dim).
        Uses Gemini API for embeddings.
        """
        if not texts:
            return np.array([])

        # Gemini embeddings API
        embeddings_list = []

        for text in texts:
            try:
                result = self.client.models.embed_content(
                    model=self.model_name,
                    contents=text,
                    config=self._config,
                )
                # Extract embedding values
                embedding = result.embeddings[0].values
                embeddings_list.append(embedding)
            except Exception as e:
                logger.warning(f"Error embedding text: {e}")
                embeddings_list.append([0.0] * EMBEDDING_DIM)

        # Convert to numpy array
        embeddings = np.array(embeddings_list, dtype=np.float32)

        # L2-normalize for cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
        embeddings = embeddings / norms

        return embeddings
