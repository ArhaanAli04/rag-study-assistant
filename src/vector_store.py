#FAISS vector store wrapper
import faiss
import numpy as np
from typing import List, Dict
from models import DocumentChunk
import json
import os
class FaissVectorStore:
    def __init__(self, embedding_dim: int):
        self.embedding_dim = embedding_dim
        self.index = faiss.IndexFlatL2(embedding_dim)  # simple L2 index
        self.metadata: List[Dict] = []  # parallel array to store metadata

    

    def add_embeddings(self, embeddings: np.ndarray, chunks: List[DocumentChunk], user_id: str | None = None):
        assert embeddings.shape[0] == len(chunks)
        self.index.add(embeddings.astype("float32"))
        for chunk in chunks:
            # NEW: extract document_id from extra_metadata
            doc_id = None
            if chunk.extra_metadata:
                doc_id = chunk.extra_metadata.get("document_id")
            self.metadata.append({
                "id": chunk.id,
                "text": chunk.text,
                "file_name": chunk.file_name,
                "page_num": chunk.page_num,
                "chunk_index": chunk.chunk_index,
                "doc_type": chunk.doc_type,
                "subject_tags": chunk.subject_tags,
                "extra_metadata": chunk.extra_metadata,
                "user_id": user_id,
                "document_id": doc_id,
            })

    def mark_delete_by_document_id(self, document_id: int):
        """
        Lazy deletion: mark chunks from this document as inactive.
        They will be filtered out at search time.
        """
        for meta in self.metadata:
            if meta.get("extra_metadata", {}).get("document_id") == document_id:
                meta["deleted"] = True
    

    def search(self, query_embedding: np.ndarray, top_k: int = 5, filters: dict | None = None):
        """
        filters example: {"user_id": "abc123", "doc_type": "pdf"}
        """
        query = query_embedding.reshape(1, -1).astype("float32")
        distances, indices = self.index.search(query, top_k * 5)  # over-fetch for filtering
        results = []

        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            meta = self.metadata[idx]
            if meta.get("deleted"):
                continue
            if filters:
                matched = True
                for k, v in filters.items():
                    if meta.get(k) != v:
                        matched = False
                        break
                if not matched:
                    continue

            results.append((float(dist), meta))
            if len(results) >= top_k:
                break

        return results

    # NEW: save index + metadata to disk
    def save(self, index_path: str, metadata_path: str):
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        faiss.write_index(self.index, index_path)
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f)

    # NEW: load index + metadata from disk
    def load(self, index_path: str, metadata_path: str):
        self.index = faiss.read_index(index_path)
        with open(metadata_path, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)
        # embedding_dim will match the loaded index
        self.embedding_dim = self.index.d