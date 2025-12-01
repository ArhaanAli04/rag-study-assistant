
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache

from query_preprocessor import (
    preprocess_query_for_vector,
    preprocess_query_for_keyword,
)
from keyword_index import BM25KeywordIndex
from reranker import CrossEncoderReranker
from index_builder import IndexBuilder
from cache import get_cached_response, set_cached_response  # your Redis helpers
from web_search_client import WebSearchClient
from web_cache import get_cached_web_results, set_cached_web_results
from web_scraper import fetch_and_extract_text
from context_compressor import SimpleContextCompressor


class RetrievalService:
    def __init__(self, index_builder: IndexBuilder, bm25_index: Optional[BM25KeywordIndex] = None):
        self.index_builder = index_builder
        self.bm25_index = bm25_index
        self.reranker = CrossEncoderReranker()
        # weights for hybrid
        self.vector_weight = 0.6
        self.keyword_weight = 0.4
        # web search client (lazy init)
        self.web_client: Optional[WebSearchClient] = None
        self.compressor = SimpleContextCompressor()

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Use the same embedding model as FAISS so local and web scores are comparable.
        Assumes IndexBuilder exposes embed_texts().
        """
        return self.index_builder.embed_texts(texts)

    # -------- L1 exact-match cache (per process) --------
    @lru_cache(maxsize=256)
    def _l1_cache_get(self, user_id: str, query: str) -> Optional[Dict[str, Any]]:
        return None  # lru_cache requires a function; we ignore this return.

    def l1_cache_lookup(self, user_id: str, query: str) -> Optional[Dict[str, Any]]:
        # lru_cache can't hold mutable objects safely; use a manual dict instead:
        return self._manual_l1_cache.get((user_id, query))

    def l1_cache_store(self, user_id: str, query: str, value: Dict[str, Any]):
        self._manual_l1_cache[(user_id, query)] = value
        if len(self._manual_l1_cache) > 256:
            # naive eviction: pop oldest
            self._manual_l1_cache.pop(next(iter(self._manual_l1_cache)))

    _manual_l1_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

    # -------- Existing semantic_search (vector only) can stay if you use it elsewhere --------
    def semantic_search(self, query: str, user_id: str | None = None, top_k: int = 5,filters: dict | None = None,):
        cached = get_cached_response(user_id, query)
        if cached is not None:
            return cached
        
        # Merge user_id into filters
        if user_id is not None:
            filters = filters.copy() if filters else {}
            filters["user_id"] = user_id

        results = self.index_builder.search(query, top_k=top_k, filters=filters)
        set_cached_response(user_id, query, results)
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
        cached = get_cached_web_results(query)
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
        set_cached_web_results(query, light_chunks)

        return chunks

    # -------- Hybrid retrieval + confidence + web fallback + rerank --------
    def hybrid_retrieve(
        self,
        query: str,
        user_id: str,
        top_k: int = 8,
        rerank_top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        Full retrieval pipeline for chat:
        - L1 exact cache
        - L2 Redis cache (through underlying index_builder if you wire it)
        - Vector + BM25 hybrid
        - Confidence scoring
        - Optional web fallback flag
        - Cross-encoder reranking
        """

        # 1. L1 exact-match cache
        cached = self.l1_cache_lookup(user_id, query)
        if cached is not None:
            return {**cached, "from_l1_cache": True}

        # 2. Preprocess queries
        vec_query = preprocess_query_for_vector(query)
        kw_query = preprocess_query_for_keyword(query)

        filters = {"user_id": user_id}

        # 3. Vector search via existing index_builder
        # vector_results: list of {"score": float, "text": str, "metadata": {...}}
        raw_vector_results = self.index_builder.search(vec_query, top_k=top_k, filters=filters)

        vector_results = []
        for item in raw_vector_results:
            # handle both tuple and dict forms safely
            if isinstance(item, dict):
                vector_results.append(item)
            else:
                # assume tuple: (score, text, metadata) or (score, metadata)
                if len(item) == 3:
                    score, text, metadata = item
                elif len(item) == 2:
                    score, metadata = item
                    text = metadata.get("text", "")
                else:
                    continue
                vector_results.append(
                    {"score": float(score), "text": text, "metadata": metadata}
                )


        # 4. BM25 search
        keyword_results = []
        if self.bm25_index is not None:
            keyword_results_raw = self.bm25_index.search(kw_query, top_k=top_k, filters=filters)
            # Convert to unified structure (BM25 scores are positive; higher is better).
            for r in keyword_results_raw:
                keyword_results.append(
                    {
                        "score": float(r["score"]),
                        "text": r["metadata"].get("text", ""),
                        "metadata": r["metadata"],
                    }
                )

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

        # 7. Confidence scoring
        if combined_list:
            best = combined_list[0]["hybrid_score"]
        else:
            best = 0.0
        # simple clamp to [0,1]; you can tune thresholds later
        confidence = max(0.0, min(1.0, best))

        # 8. Fallback decision
        fallback_used = False
        if confidence < 0.6:
            fallback_used = True

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

        result_payload: Dict[str, Any] = {
            "query": query,
            "results": reranked,
            "all_candidates": candidates,  # before compression / parent
            "confidence": confidence,
            "fallback_used": fallback_used,
            "web_results": [
                r for r in reranked if r["metadata"].get("source_type") == "web"
            ],
            
        }

        # 10. Store in L1 cache and in Redis cache (if you like)
        self.l1_cache_store(user_id, query, result_payload)
        # optional: set_cached_response(user_id, query, result_payload)

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
