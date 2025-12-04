# service that orchestrates full indexing for a given uploaded document and user.
import os
from typing import List

from chunk_builder import (
    build_chunks_from_pdf,
    build_chunks_from_pptx,
    build_chunks_from_docx,
)
from models import DocumentChunk
from index_builder import IndexBuilder
from unified_parser import DocumentParser  # if you want a generic entry point
from keyword_index import BM25KeywordIndex


class IndexingPipeline:
    def __init__(self, index_builder: IndexBuilder,bm25_index: BM25KeywordIndex):
        self.index_builder = index_builder
        self.bm25_index = bm25_index

    def _build_chunks_for_file(self, file_path: str, subject_tags: str | None = None, document_id: int | None = None) -> List[DocumentChunk]:
        ext = os.path.splitext(file_path)[-1].lower()
        if ext == ".pdf":
            return build_chunks_from_pdf(file_path, subject_tags=subject_tags, document_id=document_id)
        elif ext == ".pptx":
            return build_chunks_from_pptx(file_path, subject_tags=subject_tags, document_id=document_id)
        elif ext == ".docx":
            return build_chunks_from_docx(file_path, subject_tags=subject_tags, document_id=document_id)
        else:
            # fallback: use unified parser + generic chunking if needed
            raise ValueError(f"Unsupported extension for indexing: {ext}")

    def index_document(self, file_path: str, user_id: str | None = None, subject_tags: str | None = None, document_id: int | None = None):
        chunks = self._build_chunks_for_file(file_path, subject_tags=subject_tags, document_id=document_id)
        if not chunks:
            return 0
        #1 add to FAISS
        # IndexBuilder will call vector_store.add_embeddings; we pass user_id there
        self.index_builder.index_chunks_with_user(chunks, user_id=user_id)

        # 2) Add to BM25
        bm25_docs = []
        for c in chunks:
            # extract document_id from extra_metadata if present
            doc_id = None
            if c.extra_metadata:
                doc_id = c.extra_metadata.get("document_id")
            meta = {
                "id": c.id,
                "text": c.text,
                "file_name": c.file_name,
                "page_num": c.page_num,
                "chunk_index": c.chunk_index,
                "doc_type": c.doc_type,
                "subject_tags": c.subject_tags,
                "extra_metadata": c.extra_metadata,
                "user_id": user_id,
                "document_id": doc_id,
            }
            bm25_docs.append({"text": c.text, "metadata": meta})

        # Incremental add to BM25 index
        self.bm25_index.add_documents(bm25_docs)
        return len(chunks)
