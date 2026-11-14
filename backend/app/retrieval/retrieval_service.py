
import logging
from typing import Any, Dict, List, Optional, Protocol, Tuple

import numpy as np

from app.retrieval import confidence as conf
from app.retrieval.embeddings import EmbeddingError
from app.retrieval.pg_chunk_search import Candidates
from app.retrieval.query_preprocessor import (
    preprocess_query_for_vector,
    preprocess_query_for_keyword,
)
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.web.search_client import WebSearchClient
from app.retrieval.web.scraper import fetch_and_extract_text
from app.retrieval.context_compressor import SimpleContextCompressor

# A child of the app logger reuses its handlers; calling setup_logging() again would duplicate every line.
logger = logging.getLogger("rag_assistant.retrieval")

L1_CACHE_MAX_ENTRIES = 256


# Shapes of the Redis caches the app injects (services/caches/); declared here so retrieval never
# imports the services layer above it.
class QueryResultCache(Protocol):
    def get(self, user_id: str | None, query: str, doc_version: int) -> Optional[Any]: ...

    def set(self, user_id: str | None, query: str, doc_version: int, result: Any) -> None: ...


class WebResultCache(Protocol):
    def get(self, query: str) -> Optional[List[Dict[str, Any]]]: ...

    def set(self, query: str, results: List[Dict[str, Any]]) -> None: ...


class TextEmbedder(Protocol):
    def embed_texts(self, texts: List[str]) -> np.ndarray: ...


class ChunkSearch(Protocol):
    """The user's chunks as two candidate lists (Day 15: PgChunkSearch over document_chunks)."""

    def search(
        self, query_embedding: np.ndarray | None, keyword_query: str, user_id: str, top_k: int
    ) -> Candidates: ...

    def vector_only(
        self, query_embedding: np.ndarray, user_id: str, top_k: int, metadata_filter: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]: ...


class RetrievalService:
    def __init__(
        self,
        embedding_service: TextEmbedder,
        chunk_search: ChunkSearch,
        query_cache: QueryResultCache,
        web_cache: WebResultCache,
        web_search_enabled: bool = True,
        l1_cache_enabled: bool = True,
        vector_weight: float = 0.6,
        keyword_weight: float = 0.4,
    ) -> None:
        self.embedding_service = embedding_service
        self.chunk_search = chunk_search
        self.query_cache = query_cache
        self.web_cache = web_cache
        self.reranker = CrossEncoderReranker()
        # The retrieval eval (E4) turns web search and the L1 cache off: web results have no relevance
        # labels, and an L1 hit would replay another configuration's ranking.
        self.web_search_enabled = web_search_enabled
        self.l1_cache_enabled = l1_cache_enabled
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        # web search client (lazy init)
        self.web_client: Optional[WebSearchClient] = None
        self.compressor = SimpleContextCompressor()
        # Per instance: a class-level dict was shared by every RetrievalService in the process.
        self._l1_cache: Dict[Tuple[str, str, int], Dict[str, Any]] = {}

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        """The same embedding model as the stored chunks, so local and web scores are comparable."""
        return self.embedding_service.embed_texts(texts)

    # -------- L1 exact-match cache (per process) --------
    def l1_cache_lookup(self, user_id: str, query: str, doc_version: int) -> Optional[Dict[str, Any]]:
        return self._l1_cache.get((user_id, query, doc_version))

    def l1_cache_store(self, user_id: str, query: str, doc_version: int, value: Dict[str, Any]) -> None:
        self._l1_cache[(user_id, query, doc_version)] = value
        if len(self._l1_cache) > L1_CACHE_MAX_ENTRIES:
            # naive eviction: pop oldest
            self._l1_cache.pop(next(iter(self._l1_cache)))

    def l1_cache_purge_user(self, user_id: str) -> int:
        """Drop the user's L1 entries (account deletion); returns how many were removed."""
        stale = [key for key in self._l1_cache if key[0] == user_id]
        for key in stale:
            del self._l1_cache[key]
        return len(stale)

    # -------- semantic_search: the vector half alone (POST /search) --------
    def semantic_search(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        metadata_filter: Dict[str, Any] | None = None,
        doc_version: int = 0,
    ) -> List[Dict[str, Any]]:
        """Cosine-scored results (higher = closer; FAISS's raw distances until Day 15, B8 residual)."""
        cached = self.query_cache.get(user_id, query, doc_version)
        if cached is not None:
            return cached
        query_embedding = self._embed_texts([query])[0]
        results = self.chunk_search.vector_only(query_embedding, user_id, top_k, metadata_filter)
        self.query_cache.set(user_id, query, doc_version, results)
        return results

    def get_web_chunks(
        self,
        query: str,
        max_results: int = 5,
        chunk_size: int = 500,
        overlap: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Runs web search, filters to credible domains, optionally scrapes,
        chunks content, and returns:
        [{"text": ..., "metadata": {...}, "embedding": [...]}, ...]
        """
        # 1) Redis cache for web search results (without embeddings)
        cached = self.web_cache.get(query)
        if cached is not None:
            # Re-embed on the fly to avoid storing vectors in Redis
            texts = [c["text"] for c in cached]
            embeddings = self._embed_texts(texts)
            chunks: List[Dict[str, Any]] = []
            for base, emb in zip(cached, embeddings):
                chunks.append(
                    {
                        "text": base["text"],
                        "metadata": base["metadata"],
                        "embedding": emb,
                    }
                )
            return chunks

        # 2) Call Tavily (or SerpAPI via WebSearchClient)
        if self.web_client is None:
            self.web_client = WebSearchClient()
        results = self.web_client.search(query, max_results=max_results)

        # 3) Ensure we have decent text; optionally scrape with BeautifulSoup
        clean_results: List[Dict[str, Any]] = []
        for r in results:
            content = r.get("content") or ""
            if len(content) < 300:
                extra = fetch_and_extract_text(r["url"])
                if extra:
                    content = extra
            clean_results.append(
                {
                    "url": r["url"],
                    "title": r.get("title", ""),
                    "content": content,
                }
            )

        # 4) Chunk content
        raw_chunks: List[Dict[str, Any]] = []
        for res in clean_results:
            text = res["content"]
            if not text:
                continue
            start = 0
            while start < len(text):
                end = start + chunk_size
                chunk_text = text[start:end]
                if not chunk_text.strip():
                    break
                meta = {
                    "source_type": "web",
                    "url": res["url"],
                    "title": res["title"],
                    "offset_start": start,
                    "offset_end": end,
                }
                raw_chunks.append({"text": chunk_text, "metadata": meta})
                start = end - overlap

        # 5) Embed
        embeddings = self._embed_texts([c["text"] for c in raw_chunks])
        chunks: List[Dict[str, Any]] = []
        for c, emb in zip(raw_chunks, embeddings):
            chunks.append(
                {
                    "text": c["text"],
                    "metadata": c["metadata"],
                    "embedding": emb,
                }
            )

        # 6) Cache light version (without embeddings) with 1h TTL
        light_chunks = [
            {"text": c["text"], "metadata": c["metadata"]}
            for c in chunks
        ]
        self.web_cache.set(query, light_chunks)

        return chunks

    # -------- Hybrid retrieval + confidence + web fallback + rerank --------
    def hybrid_retrieve(
        self,
        query: str,
        user_id: str,
        doc_version: int,
        top_k: int = 8,
        rerank_top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        Full retrieval pipeline for chat:
        - L1 exact cache
        - Vector (pgvector) + keyword (Postgres full-text) hybrid
        - Confidence scoring
        - Optional web fallback flag
        - Cross-encoder reranking
        """

        # 1. L1 exact-match cache
        cached = self.l1_cache_lookup(user_id, query, doc_version) if self.l1_cache_enabled else None
        if cached is not None:
            return {**cached, "from_l1_cache": True}

        # 2. Preprocess queries
        vec_query = preprocess_query_for_vector(query)
        kw_query = preprocess_query_for_keyword(query)

        # 3–4. Vector (cosine similarity) and keyword (ts_rank_cd) candidates, both higher = better
        # and both filtered to this user inside the query (I1), in one database session (CO6).
        # A failed query embedding (a Gemini outage or quota) degrades to keyword-only search for this
        # query instead of failing the chat; the answer is still grounded in what keyword search finds.
        try:
            query_embedding: Optional[np.ndarray] = self._embed_texts([vec_query])[0]
        except EmbeddingError:
            logger.warning("Query embedding failed; keyword-only retrieval for this query", exc_info=True)
            query_embedding = None
        candidates = self.chunk_search.search(query_embedding, kw_query, user_id, top_k)
        vector_results = candidates.vector
        keyword_results = candidates.keyword

        # 5. Score normalization (min-max per list)
        def normalize_scores(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            if not results:
                return results
            scores = [r["score"] for r in results]
            s_min, s_max = min(scores), max(scores)
            if s_max == s_min:
                for r in results:
                    r["norm_score"] = 1.0
                return results
            for r in results:
                r["norm_score"] = (r["score"] - s_min) / (s_max - s_min)
            return results

        vector_results = normalize_scores(vector_results)
        keyword_results = normalize_scores(keyword_results)

        # 6. Merge hybrid scores
        combined: Dict[str, Dict[str, Any]] = {}

        def add_results(results: List[Dict[str, Any]], kind: str):
            for r in results:
                key = (r["metadata"].get("id"), r["metadata"].get("file_name"), r["metadata"].get("page_num"), r["metadata"].get("chunk_index"))
                if key not in combined:
                    meta = r["metadata"]
                    if "source_type" not in meta:
                        meta["source_type"] = "local"
                    combined[key] = {
                        "text": r.get("text", ""),
                        "metadata": meta,
                        "vector_score": 0.0,
                        "keyword_score": 0.0,
                    }
                if kind == "vector":
                    combined[key]["vector_score"] = r.get("norm_score", 0.0)
                else:
                    combined[key]["keyword_score"] = r.get("norm_score", 0.0)

        add_results(vector_results, "vector")
        add_results(keyword_results, "keyword")

        combined_list: List[Dict[str, Any]] = []
        for item in combined.values():
            vs = item["vector_score"]
            ks = item["keyword_score"]
            final_score = self.vector_weight * vs + self.keyword_weight * ks
            item["hybrid_score"] = final_score
            combined_list.append(item)

        combined_list.sort(key=lambda x: x["hybrid_score"], reverse=True)
        combined_list = combined_list[:top_k]

        # 7. Confidence scoring based on hybrid score
        confidence = 0.0

        if combined_list:
            # Factor 1: Top result score (0-50 points)
            best_score = combined_list[0]["hybrid_score"]
            score_confidence = min(50.0, best_score * 50)
            
            # Factor 2: Number of quality results (0-30 points)
            quality_results = sum(1 for c in combined_list if c["hybrid_score"] > 0.3)
            count_confidence = min(30.0, (quality_results / top_k) * 30)
            
            # Factor 3: Score distribution (0-20 points)
            if len(combined_list) >= 2:
                top_3_avg = sum(c["hybrid_score"] for c in combined_list[:3]) / min(3, len(combined_list))
                distribution_confidence = min(20.0, (top_3_avg / best_score) * 20) if best_score > 0 else 0
            else:
                distribution_confidence = 0
            
            confidence = score_confidence + count_confidence + distribution_confidence
        else:
            confidence = 0.0

        # 7.5. Enhanced topic + example heuristic:
        # If none of the top chunks contain any meaningful keyword from the query,
        # force low confidence so we rely more on web search.
        query_lower = query.lower()
        # crude keyword extraction: words longer than 4 chars
        keywords = [w for w in query_lower.split() if len(w) > 4]

        # Detect if query explicitly needs examples/numbers
        needs_example = any(word in query_lower for word in [
            "example", "numeric", "calculate", "show me", "demonstrate", 
            "instance", "case", "illustration"
        ])

        def chunk_matches(c: Dict[str, Any]) -> bool:
            text = c.get("text", "").lower()
            return any(k in text for k in keywords)

        has_matching_chunk = any(chunk_matches(c) for c in combined_list)
        has_example_in_context = any(
            "example" in c.get("text", "").lower() or 
            "e.g." in c.get("text", "").lower() or
            any(char.isdigit() for char in c.get("text", ""))  # Has numbers
            for c in combined_list
        )

        # Force web fallback if:
        # 1. No topical match AND needs example, OR
        # 2. Topical match exists but explicitly needs example AND context lacks examples
        force_web = False
        if keywords and not has_matching_chunk:
            confidence *= 0.5  # Reduce by 50%
            force_web = True
        elif needs_example and not has_example_in_context:
            confidence *= 0.6  # Reduce by 40%
            force_web = True

        if force_web:
            # B2: this was min(confidence, 0.3) — 0 on the 0–100 scale.
            confidence = min(confidence, conf.FORCED_WEB_CAP)
        confidence = max(conf.CONFIDENCE_MIN, min(conf.CONFIDENCE_MAX, confidence))
        # 8. Fallback decision (now uses adjusted confidence)
        fallback_used = confidence < conf.WEB_FALLBACK_BELOW


        # 9. Build candidates from local results
        candidates: List[Dict[str, Any]] = []
        for c in combined_list:
            candidates.append(
                {
                    "text": c["text"],
                    "metadata": c["metadata"],
                    "score": c["hybrid_score"],
                }
            )

        # 9.5. Add web chunks (if fallback or always-on)
        web_chunks: List[Dict[str, Any]] = []
        if self.web_search_enabled:
            try:
                if fallback_used:
                    web_chunks = self.get_web_chunks(query, max_results=3)
                else:
                    # optional: still enrich with a couple of web chunks
                    web_chunks = self.get_web_chunks(query, max_results=2)
            except Exception:
                web_chunks = []

        for wc in web_chunks:
            meta = wc["metadata"]
            meta["source_type"] = "web"
            candidates.append(
                {
                    "text": wc["text"],
                    "metadata": meta,
                    "score": 0.5,  # neutral base score; cross-encoder will refine
                }
            )

        # 10. Rerank using cross-encoder across local + web
        reranked = self.reranker.rerank(query, candidates, top_k=rerank_top_k)

        # 10.5 Recalculate confidence based on FINAL reranked results
        final_confidence = confidence  # Start with hybrid confidence

        if reranked and len(reranked) > 0:
            # Check if we have web results in top results
            web_count = sum(1 for r in reranked if r["metadata"].get("source_type") == "web")
            
            if web_count > 0 and final_confidence < conf.WEB_RESCORE_BELOW:
                # We relied on web fallback - set moderate confidence
                # Based on: number of results + reranker scores
                top_scores = [r.get("score", 0) for r in reranked[:3]]
                avg_score = sum(top_scores) / len(top_scores) if top_scores else 0

                web_confidence = min(
                    conf.WEB_CONFIDENCE_CEILING,
                    conf.WEB_CONFIDENCE_FLOOR + (len(reranked) * 5) + (avg_score * 20),
                )
                final_confidence = max(final_confidence, web_confidence)
                logger.debug("Web fallback confidence: %.1f (avg rerank score: %.3f)", web_confidence, avg_score)

        result_payload: Dict[str, Any] = {
            "query": query,
            "results": reranked,
            "all_candidates": candidates,  # before compression / parent
            "confidence": final_confidence,
            "fallback_used": fallback_used,
            "web_results": [
                r for r in reranked if r["metadata"].get("source_type") == "web"
            ],
            
        }

        # A degraded (keyword-only) result isn't cached: the same question should get full retrieval
        # once embeddings work again, not a replay of the degraded ranking until the next upload.
        if self.l1_cache_enabled and query_embedding is not None:
            self.l1_cache_store(user_id, query, doc_version, result_payload)

        return result_payload
    
    def expand_to_parent_context(
        self,
        top_results: List[Dict[str, Any]],
        all_results: List[Dict[str, Any]],
        max_parents: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Given top child chunks (top_results) and the full candidate set (all_results),
        group by (document_id, page_num) and return broader context.
        """
        if not top_results:
            return []

        # Collect target (doc_id, page_num) pairs from top results
        targets = set()
        for r in top_results:
            meta = r["metadata"]
            doc_id = meta.get("extra_metadata", {}).get("document_id")
            page = meta.get("page_num")
            if doc_id is not None and page is not None:
                targets.add((doc_id, page))

        parent_map: Dict[tuple, Dict[str, Any]] = {}
        for r in all_results:
            meta = r["metadata"]
            doc_id = meta.get("extra_metadata", {}).get("document_id")
            page = meta.get("page_num")
            key = (doc_id, page)
            if key not in targets:
                continue
            if key not in parent_map:
                parent_map[key] = {
                    "text": "",
                    "metadata": {
                        **meta,
                        "parent_page": page,
                    },
                }
            parent_map[key]["text"] += "\n" + r.get("text", "")

        parents = list(parent_map.values())
        # Limit count
        return parents[:max_parents]
