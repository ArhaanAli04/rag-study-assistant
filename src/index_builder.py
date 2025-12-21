#batch processing for embedding generation
from typing import List
from tqdm import tqdm

from models import DocumentChunk
from embedding_service import EmbeddingService
from vector_store import FaissVectorStore


class IndexBuilder:
    def __init__(self, embedding_model_name: str = "gemini-embedding-001"):
        # Initialize embedding service
        self.embedding_service = EmbeddingService(embedding_model_name)

        # Infer embedding dimension from a dummy call
        dummy_emb = self.embedding_service.embed_texts(["hello world"])
        self.vector_store = FaissVectorStore(embedding_dim=dummy_emb.shape[1])

     # NEW: generic embedding helper for web chunks etc.
    def embed_texts(self, texts: List[str]):
        """
        Expose the underlying embedding model so other components
        (e.g. RetrievalService) can encode arbitrary texts.
        """
        return self.embedding_service.embed_texts(texts)

    def index_chunks(self, chunks: List[DocumentChunk], batch_size: int = 32):
        """Backward-compatible: index chunks without user_id."""
        self.index_chunks_with_user(chunks, user_id=None, batch_size=batch_size)

    def index_chunks_with_user(self, chunks: List[DocumentChunk], user_id: str | None, batch_size: int = 32):
        """New: index chunks and tag them with user_id in metadata."""
        texts = [c.text for c in chunks]
        num_chunks = len(chunks)

        for start in tqdm(range(0, num_chunks, batch_size), desc="Indexing chunks"):
            end = min(start + batch_size, num_chunks)
            batch_texts = texts[start:end]
            batch_chunks = chunks[start:end]
            embeddings = self.embedding_service.embed_texts(batch_texts)
            # IMPORTANT change: pass user_id here
            self.vector_store.add_embeddings(embeddings, batch_chunks, user_id=user_id)

    def search(self, query: str, top_k: int = 5,filters: dict | None = None):
        """
        High-level search: embed query and search vector store.
        """
        query_embedding = self.embedding_service.embed_texts([query])[0]
        return self.vector_store.search(query_embedding, top_k=top_k, filters=filters)

    def get_index(self) -> FaissVectorStore:
        return self.vector_store
