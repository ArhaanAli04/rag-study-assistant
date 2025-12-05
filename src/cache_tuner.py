"""
Test semantic cache hit rates at different similarity thresholds.
"""
from semantic_cache import SemanticCache
from main import index_builder, semantic_cache
from typing import List

TEST_QUERIES = [
    "What is supervised learning?",
    "Explain confusion matrix",
    "What is overfitting?",
    "cross validation",
    "gradient descent"
] * 5  # repeat for stable stats

THRESHOLDS = [0.90, 0.92, 0.95, 0.98]

def tune_cache_thresholds():
    print("=== Semantic Cache Threshold Tuning ===")
    
    # Clear cache first
    #semantic_cache.clear()
    
    first_run_hits = {t: 0 for t in THRESHOLDS}
    
    for query in TEST_QUERIES:
        # First run - should all MISS
        for thresh in THRESHOLDS:
            hit = semantic_cache.lookup(query, threshold=thresh) is not None
            if hit:
                first_run_hits[thresh] += 1
    
    print("First run (expected all MISS):")
    for t, hits in first_run_hits.items():
        print(f"  Threshold {t}: {hits}/{len(TEST_QUERIES)} hits")
    
    # Second run - should all HIT
    second_run_hits = {t: 0 for t in THRESHOLDS}
    for query in TEST_QUERIES:
        for thresh in THRESHOLDS:
            hit = semantic_cache.lookup(query, threshold=thresh) is not None
            if hit:
                second_run_hits[thresh] += 1
    
    print("\nSecond run (expected all HIT):")
    for t, hits in second_run_hits.items():
        hit_rate = hits / len(TEST_QUERIES) * 100
        print(f"  Threshold {t}: {hits}/{len(TEST_QUERIES)} hits ({hit_rate:.1f}%)")

if __name__ == "__main__":
    tune_cache_thresholds()
