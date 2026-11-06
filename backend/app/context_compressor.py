from typing import List, Dict, Any
import heapq


class SimpleContextCompressor:
    """
    Heuristic compressor that:
    - Limits number of chunks
    - Optionally truncates each chunk to a max length
    - Prefers higher-scoring chunks
    """

    def __init__(self, max_chunks: int = 6, max_chars_per_chunk: int = 800):
        self.max_chunks = max_chunks
        self.max_chars_per_chunk = max_chars_per_chunk

    def compress(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        results: [{"text": ..., "metadata": {...}, "score": ..., "rerank_score": ...}, ...]
        Returns a smaller list of results, keeping the strongest evidence.
        """
        if not results:
            return []

        # Use rerank_score when available, else score/hybrid_score fallback
        def score_of(r: Dict[str, Any]) -> float:
            if "rerank_score" in r:
                return float(r["rerank_score"])
            if "score" in r:
                return float(r["score"])
            if "hybrid_score" in r:
                return float(r["hybrid_score"])
            return 0.0

        # Take top N by score
        top = heapq.nlargest(self.max_chunks, results, key=score_of)

        # Truncate text per chunk
        compressed: List[Dict[str, Any]] = []
        for r in top:
            text = r.get("text", "")
            if len(text) > self.max_chars_per_chunk:
                text = text[: self.max_chars_per_chunk]
            r2 = dict(r)
            r2["text"] = text
            compressed.append(r2)

        return compressed
