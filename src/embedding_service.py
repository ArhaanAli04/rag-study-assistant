from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List
from sklearn.preprocessing import normalize

class EmbeddingService:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        Returns a 2D numpy array of shape (len(texts), embedding_dim).
        """
        embeddings = self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
         # L2-normalize for cosine similarity via dot product / L2
        embeddings = normalize(embeddings)
        return embeddings
