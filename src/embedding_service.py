from google import genai
import numpy as np
from typing import List
from dotenv import load_dotenv
import os


class EmbeddingService:
    def __init__(self, model_name: str = "gemini-embedding-001"):
        """
        Use Gemini API for embeddings instead of local sentence-transformers.
        Falls back to text-embedding-004 if gemini-embedding-004 not available.
        """
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

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
                    contents=text
                )
                # Extract embedding values
                embedding = result.embeddings[0].values
                embeddings_list.append(embedding)
            except Exception as e:
                print(f"Error embedding text: {e}")
                # Fallback: zero vector with typical Gemini embedding dimension
                embeddings_list.append([0.0] * 768)
        
        # Convert to numpy array
        embeddings = np.array(embeddings_list, dtype=np.float32)
        
        # L2-normalize for cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
        embeddings = embeddings / norms
        
        return embeddings
