"""python -m eval.retrieval --config baseline [--label before-b8] [--limit 10]   (run from backend/)

Needs GEMINI_API_KEY for the first run (embeddings; later runs hit the on-disk cache), and
TAVILY_API_KEY only for --config web. No Redis, no database. GEMINI_API_KEY must be the eval
project's key, set as an environment variable; the run refuses to start on .env's production key.
"""
import argparse
import logging
from pathlib import Path

from app.core.gemini import build_gemini_client
from eval.retrieval.configs import CONFIGS
from eval.retrieval.corpus import index_corpus
from eval.retrieval.dataset import load_questions, problems_against_corpus
from eval.retrieval.embedding_cache import CachedEmbeddingService
from eval.retrieval.key_guard import assert_eval_key
from eval.retrieval.rate_limit import EMBEDDING_RPM, EMBEDDING_TPM, RateLimiter
from eval.retrieval.runner import RESULTS_DIR, run, write_results

DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "datasets" / "retrieval_v1.jsonl"

logger = logging.getLogger("eval.retrieval")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m eval.retrieval", description="Retrieval eval (E4)")
    parser.add_argument("--config", required=True, choices=sorted(CONFIGS))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--label", help="suffix for the result files, e.g. before-b8")
    parser.add_argument("--limit", type=int, help="only the first N questions (smoke runs)")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = CONFIGS[args.config]
    questions = load_questions(args.dataset)
    if args.limit:
        questions = questions[: args.limit]

    assert_eval_key()
    embeddings = CachedEmbeddingService(
        build_gemini_client(), limiter=RateLimiter(EMBEDDING_RPM, EMBEDDING_TPM)
    )
    try:
        corpus = index_corpus(embeddings)
        indexing_calls = embeddings.api_calls
        problems = problems_against_corpus(questions, corpus.page_texts())
        if problems:
            raise SystemExit("dataset does not match the corpus:\n  " + "\n  ".join(problems))
        result = run(config, corpus, questions, args.dataset)
        result.meta["embedding_cache"] = {
            "hits": embeddings.hits,
            "api_calls": embeddings.api_calls,
            "api_calls_indexing": indexing_calls,
        }
    finally:
        embeddings.close()

    for path in write_results(result, args.results_dir, args.label):
        logger.info("wrote %s", path)


if __name__ == "__main__":
    main()
