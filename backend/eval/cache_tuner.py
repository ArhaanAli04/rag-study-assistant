"""
Test semantic cache hit rates at different similarity thresholds.

Run from backend/: python -m eval.cache_tuner (needs the real .env, Gemini and Redis).
It only looks entries up, so hits come from what the first user's semantic cache already holds.
CO5 (Day 32) replaces it.
"""
from app.db.database import SessionLocal, User
from app.services.caches.semantic_cache import SemanticCache
from app.services.container import build_services

TEST_QUERIES = [
    "What is supervised learning?",
    "Explain confusion matrix",
    "What is overfitting?",
    "cross validation",
    "gradient descent"
] * 5  # repeat for stable stats

THRESHOLDS = [0.90, 0.92, 0.95, 0.98]
MODE = "detailed"

def tune_cache_thresholds(semantic_cache: SemanticCache, user_id: int, doc_version: int) -> None:
    print("=== Semantic Cache Threshold Tuning ===")

    first_run_hits = {t: 0 for t in THRESHOLDS}

    for query in TEST_QUERIES:
        # First run - should all MISS
        for thresh in THRESHOLDS:
            hit = semantic_cache.lookup(query, user_id, doc_version, MODE, threshold=thresh) is not None
            if hit:
                first_run_hits[thresh] += 1

    print("First run (expected all MISS):")
    for t, hits in first_run_hits.items():
        print(f"  Threshold {t}: {hits}/{len(TEST_QUERIES)} hits")

    # Second run - should all HIT
    second_run_hits = {t: 0 for t in THRESHOLDS}
    for query in TEST_QUERIES:
        for thresh in THRESHOLDS:
            hit = semantic_cache.lookup(query, user_id, doc_version, MODE, threshold=thresh) is not None
            if hit:
                second_run_hits[thresh] += 1

    print("\nSecond run (expected all HIT):")
    for t, hits in second_run_hits.items():
        hit_rate = hits / len(TEST_QUERIES) * 100
        print(f"  Threshold {t}: {hits}/{len(TEST_QUERIES)} hits ({hit_rate:.1f}%)")

def main() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).first()
        user_id, doc_version = user.id, user.doc_version
    finally:
        db.close()

    services = build_services()
    try:
        tune_cache_thresholds(services.semantic_cache, user_id, doc_version)
    finally:
        services.close()

if __name__ == "__main__":
    main()
