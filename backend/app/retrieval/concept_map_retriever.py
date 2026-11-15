"""Retrieval for concept maps: the app's shared RetrievalService with concept-map settings."""

import logging
from typing import Any, Dict, List

from app.retrieval.embeddings import EmbeddingError
from app.retrieval.retrieval_service import RetrievalService
from app.retrieval.web.search_client import WEB_SEARCH_ERRORS

logger = logging.getLogger(__name__)

# A web-only map has no hybrid score to derive confidence from.
WEB_ONLY_CONFIDENCE = 70.0
WEB_ONLY_SCORE = 0.8


class ConceptMapRetriever:
    def __init__(self, retrieval_service: RetrievalService) -> None:
        # The app's shared service: a private one searched an index /upload never wrote to (R5).
        self.retrieval_service = retrieval_service

    def retrieve_for_concept_map(
        self,
        topic: str,
        user_id: str,
        doc_version: int,
        use_documents: bool = False,
        use_web: bool = True,
        max_results: int = 15,
    ) -> Dict[str, Any]:
        """Retrieve context for a concept map.

        doc_version has no default: it is part of the L1 cache key, and a constant one replayed a
        ranking from before the user's last upload or delete (a deleted file kept appearing in maps).

        Returns combined_results, document_results, web_results, sources (counts and names), topic
        and confidence.
        """
        logger.info("Concept-map retrieval: documents=%s web=%s", use_documents, use_web)

        all_results: List[Dict[str, Any]] = []
        document_results: List[Dict[str, Any]] = []
        web_results: List[Dict[str, Any]] = []
        confidence = 0.0

        if use_documents:
            result = self.retrieval_service.hybrid_retrieve(
                query=topic,
                user_id=user_id,
                doc_version=doc_version,
                top_k=max_results,
                rerank_top_k=max_results,
                include_web=use_web,
            )
            all_results = result.get("results", [])
            confidence = result.get("confidence", 0.0)
            for r in all_results:
                if r.get("metadata", {}).get("source_type", "local") == "web":
                    web_results.append(r)
                else:
                    document_results.append(r)
        elif use_web:
            try:
                web_chunks = self.retrieval_service.get_web_chunks(
                    query=topic,
                    max_results=max_results,
                    chunk_size=800,  # larger than chat's: a map needs whole explanations, not snippets
                    overlap=100,
                )
            except (*WEB_SEARCH_ERRORS, EmbeddingError):
                logger.warning("Web search for a concept map failed", exc_info=True)
            else:
                web_results = [
                    {"text": c["text"], "metadata": c["metadata"], "score": WEB_ONLY_SCORE} for c in web_chunks
                ]
                all_results = web_results
                confidence = WEB_ONLY_CONFIDENCE if web_results else 0.0
        else:
            logger.warning("Concept-map retrieval with both documents and web off")

        sources = {
            "total": len(all_results),
            "documents": len(document_results),
            "web": len(web_results),
            "document_sources": self._extract_document_sources(document_results),
            "web_sources": self._extract_web_sources(web_results),
        }
        logger.info(
            "Concept-map retrieval: %d results (%d documents, %d web), confidence %.1f",
            sources["total"], sources["documents"], sources["web"], confidence,
        )
        return {
            "combined_results": all_results,
            "document_results": document_results,
            "web_results": web_results,
            "sources": sources,
            "topic": topic,
            "confidence": confidence,
        }

    def _extract_document_sources(self, results: List[Dict[str, Any]]) -> List[str]:
        names = {r.get("metadata", {}).get("file_name") for r in results}
        return sorted(name for name in names if name)

    def _extract_web_sources(self, results: List[Dict[str, Any]]) -> List[str]:
        urls = {r.get("metadata", {}).get("url") for r in results}
        return sorted(url for url in urls if url)
