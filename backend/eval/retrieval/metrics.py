"""Ranking metrics in plain Python, over ranked lists of (file_name, page) keys.

Relevance is labelled per page, but retrieval returns chunks, and several chunks can come from the
same page. Only the first chunk of a relevant page earns gain; later ones keep their rank position
but earn nothing, so Recall stays ≤ 1 and nDCG ≤ 1.
"""
import math
import random
from statistics import fmean
from typing import Optional, Sequence, Set, Tuple

PageKey = Tuple[str, Optional[int]]


def gains(ranked: Sequence[PageKey], relevant: Set[PageKey]) -> list[int]:
    seen: Set[PageKey] = set()
    result: list[int] = []
    for page in ranked:
        if page in relevant and page not in seen:
            seen.add(page)
            result.append(1)
        else:
            result.append(0)
    return result


def hit_at_k(ranked: Sequence[PageKey], relevant: Set[PageKey], k: int) -> float:
    """1.0 if any relevant page is in the top k. The headline metric: one answering page in the
    model's context is usually enough, even when several pages could answer."""
    if not relevant:
        raise ValueError("hit rate is undefined without relevant pages")
    return 1.0 if any(page in relevant for page in ranked[:k]) else 0.0


def recall_at_k(ranked: Sequence[PageKey], relevant: Set[PageKey], k: int) -> float:
    if not relevant:
        raise ValueError("recall is undefined without relevant pages")
    return sum(gains(ranked, relevant)[:k]) / len(relevant)


def reciprocal_rank(ranked: Sequence[PageKey], relevant: Set[PageKey], k: int) -> float:
    for position, gain in enumerate(gains(ranked, relevant)[:k], start=1):
        if gain:
            return 1.0 / position
    return 0.0


def _dcg(gain_list: Sequence[int]) -> float:
    return sum(gain / math.log2(position + 1) for position, gain in enumerate(gain_list, start=1))


def ndcg_at_k(ranked: Sequence[PageKey], relevant: Set[PageKey], k: int) -> float:
    if not relevant:
        raise ValueError("nDCG is undefined without relevant pages")
    ideal = _dcg([1] * min(len(relevant), k))
    return _dcg(gains(ranked, relevant)[:k]) / ideal


def bootstrap_ci(
    values: Sequence[float], resamples: int = 2000, alpha: float = 0.05, seed: int = 0
) -> Tuple[float, float]:
    """Percentile bootstrap interval for the mean; seeded so a re-run gives the same interval."""
    if not values:
        raise ValueError("no values")
    rng = random.Random(seed)
    n = len(values)
    means = sorted(fmean(rng.choices(values, k=n)) for _ in range(resamples))
    low = means[int((alpha / 2) * resamples)]
    high = means[min(resamples - 1, int((1 - alpha / 2) * resamples))]
    return low, high


def auc(positive_scores: Sequence[float], negative_scores: Sequence[float]) -> Optional[float]:
    """P(a random positive scores above a random negative), ties counting half (Mann-Whitney U).

    None when either side is empty: with no misses (or no hits) the score can't be said to
    separate them.
    """
    if not positive_scores or not negative_scores:
        return None
    wins = 0.0
    for p in positive_scores:
        for n in negative_scores:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(positive_scores) * len(negative_scores))
