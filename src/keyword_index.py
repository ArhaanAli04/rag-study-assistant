#keyword based search index
from rank_bm25 import BM25Okapi  # [web:2]
from typing import List, Dict
import numpy as np


class BM25KeywordIndex:
    def __init__(self):
        self.tokenized_corpus: List[List[str]] = []
        self.metadata: List[Dict] = []
        self.bm25: BM25Okapi | None = None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        # Very simple tokenizer; you can improve later.
        return text.lower().split()

    def build(self, docs: List[Dict]):
        """
        docs: list of {"text": str, "metadata": {...}}
        """
        self.tokenized_corpus = [self._tokenize(d["text"]) for d in docs]
        self.metadata = [d["metadata"] for d in docs]
        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)  # [web:2]

    def add_documents(self, docs: List[Dict]):
        """
        Incrementally add docs; then rebuild BM25.
        """
        new_tokens = [self._tokenize(d["text"]) for d in docs]
        self.tokenized_corpus.extend(new_tokens)
        self.metadata.extend([d["metadata"] for d in docs])
        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)

    def search(self, query: str, top_k: int = 5, filters: Dict | None = None):
        if not self.bm25:
            return []
        tokenized_query = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)  # [web:2]
        # sort descending
        indices = np.argsort(scores)[::-1]
        results = []
        for idx in indices:
            meta = self.metadata[idx]
            if filters:
                ok = True
                for k, v in filters.items():
                    if meta.get(k) != v:
                        ok = False
                        break
                if not ok:
                    continue
            results.append({"score": float(scores[idx]), "metadata": meta})
            if len(results) >= top_k:
                break
        return results
