"""python -m eval.generation --model gemini-3.5-flash-lite [--ids g-001,h-01] [--limit N] [--label …]
python -m eval.generation --probe gemini-2.5-flash-lite        (one tiny call: is the model served to this key?)

Run from backend/ with GEMINI_API_KEY set to the eval project's key (the run refuses .env's
production key). No Redis, no database. The corpus is re-indexed from the Day 11 embedding cache.
"""
import argparse
import logging
from pathlib import Path
from typing import List

from google import genai
from google.genai import errors as genai_errors

from app.core.gemini import build_gemini_client
from eval.generation.answer_cache import ResultCache
from eval.generation.judge import DEFAULT_JUDGE_MODEL
from eval.generation.runner import DEFAULT_MODE, build_context, run, write_results
from eval.retrieval.corpus import index_corpus, sha256_of
from eval.retrieval.dataset import EvalQuestion, load_questions, problems_against_corpus
from eval.retrieval.embedding_cache import CachedEmbeddingService
from eval.retrieval.key_guard import assert_eval_key
from eval.retrieval.rate_limit import EMBEDDING_RPM, EMBEDDING_TPM, RateLimiter
from eval.retrieval.runner import RESULTS_DIR

DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "datasets" / "retrieval_v1.jsonl"
DEFAULT_MODEL = "gemini-3.5-flash-lite"

logger = logging.getLogger("eval.generation")


def probe(client: genai.Client, model: str) -> bool:
    """One request, never cached: does this key get answers from this model at all? (2.5 models
    are limited to projects that used them before, and the eval project is new.)"""
    try:
        response = client.models.generate_content(model=model, contents="Reply with the single word OK.")
    except genai_errors.APIError as exc:
        logger.error("probe %s: refused — HTTP %s %s: %s", model, exc.code, exc.status, str(exc.message)[:300])
        return False
    logger.info("probe %s: served — reply %r", model, (response.text or "").strip()[:40])
    return True


def select(questions: List[EvalQuestion], ids: str | None, limit: int | None) -> List[EvalQuestion]:
    if ids:
        wanted = [i.strip() for i in ids.split(",") if i.strip()]
        by_id = {q.id: q for q in questions}
        missing = [i for i in wanted if i not in by_id]
        if missing:
            raise SystemExit(f"unknown question ids: {', '.join(missing)}")
        questions = [by_id[i] for i in wanted]
    return questions[:limit] if limit else questions


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m eval.generation", description="Generation eval (E1, E2)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="the answering model")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--mode", default=DEFAULT_MODE, choices=["quick", "detailed", "step_by_step"])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--ids", help="comma-separated question ids, in this order")
    parser.add_argument("--limit", type=int, help="only the first N questions (after --ids)")
    parser.add_argument("--label", help="suffix for the result files")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--probe", metavar="MODEL", help="make one call to MODEL, report, and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    assert_eval_key()
    client = build_gemini_client()
    if args.probe:
        raise SystemExit(0 if probe(client, args.probe) else 3)

    questions = select(load_questions(args.dataset), args.ids, args.limit)
    embeddings = CachedEmbeddingService(client, limiter=RateLimiter(EMBEDDING_RPM, EMBEDDING_TPM))
    cache = ResultCache()
    try:
        corpus = index_corpus(embeddings)
        problems = problems_against_corpus(questions, corpus.page_texts())
        if problems:
            raise SystemExit("dataset does not match the corpus:\n  " + "\n  ".join(problems))
        ctx = build_context(client, corpus, cache, args.model, args.judge_model, args.mode)
        meta = {"dataset": {"path": args.dataset.name, "sha256": sha256_of(args.dataset), "questions": len(questions)}}
        result = run(ctx, questions, meta)
        result.meta["embedding_cache"] = {"hits": embeddings.hits, "api_calls": embeddings.api_calls}
    finally:
        embeddings.close()
        cache.close()

    for path in write_results(result, args.results_dir, args.label):
        logger.info("wrote %s", path)
    if not result.complete:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
