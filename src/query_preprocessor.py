import re
from typing import List

# Very lightweight preprocessing. You can swap parts later (e.g. spell correction library).

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are",
    "was", "were", "be", "been", "this", "that", "these", "those", "it", "as", "by",
    "at", "from", "about", "into", "over", "after", "before", "between", "up", "down",
}


def basic_normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def remove_stopwords(tokens: List[str]) -> List[str]:
    return [t for t in tokens if t not in STOPWORDS]


def preprocess_query_for_vector(query: str) -> str:
    """
    For vector search we mostly normalize; stopword removal can hurt semantics.
    """
    return basic_normalize(query)


def preprocess_query_for_keyword(query: str) -> str:
    """
    For BM25 we normalize + remove stopwords.
    """
    norm = basic_normalize(query)
    tokens = norm.split()
    tokens = remove_stopwords(tokens)
    return " ".join(tokens)


def expand_query(query: str) -> str:
    """
    Very small hook for query expansion.
    For now, just return normalized query; you can add synonyms later.
    """
    return basic_normalize(query)
