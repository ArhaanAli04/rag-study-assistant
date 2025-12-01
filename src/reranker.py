#re-ranking layer
from typing import List, Dict, Any, Tuple
from sentence_transformers import CrossEncoder  # [web:30][web:46]


class CrossEncoderReranker:
    """
    Lightweight wrapper around a cross-encoder model for reranking.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        # This is small enough for dev; you can change to a faster/slower one later. [web:38]
        self.model = CrossEncoder(model_name)

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int | None = None,
    ) -> List[Dict[str, Any]]:
        """
        candidates: list of {"text": str, "metadata": {...}, "score": float}
        Returns same structure but sorted by cross-encoder score (desc) and
        adds "rerank_score" to each.
        """
        if not candidates:
            return []

        pairs: List[Tuple[str, str]] = [(query, c["text"]) for c in candidates]
        scores = self.model.predict(pairs)  # higher = more relevant [web:46]

        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)

        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        if top_k is not None:
            candidates = candidates[:top_k]
        return candidates
