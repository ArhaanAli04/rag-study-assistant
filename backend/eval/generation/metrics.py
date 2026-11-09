"""Generation metrics and agreement statistics in plain Python.

Faithfulness is supported claims / all claims of one answer, so a long answer can't hide one
invented fact behind many true ones any more than a short one can. Claim-level rates
(contradicted, not_in_context) are pooled over all claims of a slice.
"""
import random
from collections import Counter
from statistics import fmean
from typing import Dict, Hashable, List, Optional, Sequence, Tuple

from eval.generation.judge import FaithfulnessVerdict

GROUNDING_BANDS = ("strict", "loose", "none")


def faithfulness_score(verdict: FaithfulnessVerdict) -> Optional[float]:
    """None for an answer with no claims (a pure refusal): there is nothing to be faithful about."""
    if not verdict.claims:
        return None
    return sum(1 for c in verdict.claims if c.verdict == "supported") / len(verdict.claims)


def rate(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator else None


# ---------- agreement ----------

def percent_agreement(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    _check_pairs(a, b)
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


def cohen_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> Optional[float]:
    """κ = (pₒ − pₑ) / (1 − pₑ). None when pₑ = 1 (both raters used one and the same label for
    everything): agreement is then guaranteed and says nothing about the judge."""
    _check_pairs(a, b)
    n = len(a)
    observed = percent_agreement(a, b)
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[label] * count_b[label] for label in set(a) | set(b)) / (n * n)
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


def weighted_kappa(a: Sequence[Hashable], b: Sequence[Hashable], order: Sequence[Hashable]) -> Optional[float]:
    """Linearly weighted κ for ordinal labels: a one-step disagreement (full vs partial) costs half
    of a two-step one (full vs off_topic)."""
    _check_pairs(a, b)
    position = {label: i for i, label in enumerate(order)}
    unknown = (set(a) | set(b)) - set(position)
    if unknown:
        raise ValueError(f"labels outside the order: {sorted(map(str, unknown))}")
    steps = max(len(order) - 1, 1)
    n = len(a)

    def disagreement(x: Hashable, y: Hashable) -> float:
        return abs(position[x] - position[y]) / steps

    observed = sum(disagreement(x, y) for x, y in zip(a, b)) / n
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[x] * count_b[y] * disagreement(x, y) for x in count_a for y in count_b) / (n * n)
    if expected == 0:
        return None
    return 1 - observed / expected


def _check_pairs(a: Sequence[Hashable], b: Sequence[Hashable]) -> None:
    if len(a) != len(b) or not a:
        raise ValueError("agreement needs two equally long, non-empty label lists")


# ---------- paired comparison ----------

def paired_difference(
    after: Sequence[float], before: Sequence[float], resamples: int = 2000, alpha: float = 0.05, seed: int = 0
) -> Tuple[float, Tuple[float, float]]:
    """Mean of (after − before) over questions both models answered, with a percentile bootstrap
    interval that resamples questions, keeping each pair together. Seeded: a re-run gives the
    same interval."""
    if len(after) != len(before) or not after:
        raise ValueError("a paired difference needs two equally long, non-empty lists")
    diffs = [x - y for x, y in zip(after, before)]
    rng = random.Random(seed)
    means = sorted(fmean(rng.choices(diffs, k=len(diffs))) for _ in range(resamples))
    low = means[int((alpha / 2) * resamples)]
    high = means[min(resamples - 1, int((1 - alpha / 2) * resamples))]
    return fmean(diffs), (low, high)


def by_band(values: Sequence[Tuple[str, Optional[float]]]) -> Dict[str, List[float]]:
    """(grounding band, score) pairs → scores per band, dropping answers with no score."""
    bands: Dict[str, List[float]] = {band: [] for band in GROUNDING_BANDS}
    for band, score in values:
        if score is not None:
            bands.setdefault(band, []).append(score)
    return bands
