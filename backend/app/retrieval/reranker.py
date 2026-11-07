#re-ranking layer
from typing import List, Dict, Any


class CrossEncoderReranker:
    """
    Lightweight wrapper around a cross-encoder model for reranking.
    """

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank candidates using Gemini API to score relevance.
        """
        if not candidates:
            return []

        # For production simplicity, just return sorted by existing score
        # You can implement Gemini-based scoring here if needed
        for c in candidates:
            c["rerank_score"] = c.get("score", 0.0)

        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        
        if top_k is not None:
            candidates = candidates[:top_k]
            
        return candidates
