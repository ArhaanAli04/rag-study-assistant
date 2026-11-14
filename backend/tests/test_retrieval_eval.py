"""E4: the retrieval eval harness — metrics on hand-worked rankings, dataset validation, the
embedding cache, and one offline end-to-end run over a sample PDF."""
import json
import math
import shutil
import types
from pathlib import Path
from typing import Any, Dict, List

import pytest

from eval.retrieval import metrics
from eval.retrieval.configs import CONFIGS
from eval.retrieval.corpus import CorpusError, CorpusFile, index_corpus, verify_corpus, write_manifest
from eval.retrieval.dataset import (
    DatasetError,
    EvalQuestion,
    RelevantPage,
    load_questions,
    problems_against_corpus,
    write_questions,
)
from eval.retrieval.embedding_cache import CachedEmbeddingService, EmbeddingFailure
from eval.retrieval.generate_questions import (
    GeneratedQuestion,
    is_daily_quota,
    lexical_overlap,
    load_progress,
    quotas,
    review,
    run_generation,
)
from eval.retrieval.key_guard import ProductionKeyError, assert_eval_key
from eval.retrieval.rate_limit import EMBEDDING_RPM, EMBEDDING_TPM, RateLimiter, estimate_tokens
from app.ingestion.models import DocumentChunk
from google.genai import errors as genai_errors
from eval.retrieval.runner import evidence_status, render_markdown, run, write_results
from app.db.session import SessionLocal
from app.retrieval.context_assembly import AssembledContext
from tests.fakes import FakeGenaiClient

QUOTA_ERROR = genai_errors.ClientError(429, {"error": {"code": 429, "message": "RESOURCE_EXHAUSTED"}})

SAMPLES = Path(__file__).parent / "samples"
A1, A2, A3, B1 = ("a.pdf", 1), ("a.pdf", 2), ("a.pdf", 3), ("b.pdf", 1)


# ---------- metrics ----------

def test_relevant_at_rank_3_of_10() -> None:
    ranked = [B1, A2, A1] + [("x.pdf", i) for i in range(7)]

    assert metrics.recall_at_k(ranked, {A1}, 5) == 1.0
    assert metrics.recall_at_k(ranked, {A1}, 2) == 0.0
    assert metrics.reciprocal_rank(ranked, {A1}, 10) == pytest.approx(1 / 3)
    assert metrics.ndcg_at_k(ranked, {A1}, 10) == pytest.approx(1 / math.log2(4)) == pytest.approx(0.5)


def test_hit_at_k_needs_only_one_of_several_pages() -> None:
    # A single-intent question answered on three slides: one in the top 5 is a full hit,
    # while Recall@5 would call it a third.
    ranked = [B1, A3, ("x.pdf", 1)]

    assert metrics.hit_at_k(ranked, {A1, A2, A3}, 5) == 1.0
    assert metrics.recall_at_k(ranked, {A1, A2, A3}, 5) == pytest.approx(1 / 3)
    assert metrics.hit_at_k(ranked, {A1}, 5) == 0.0


def test_reciprocal_rank_respects_the_cutoff() -> None:
    ranked = [B1] * 5 + [A1]

    assert metrics.reciprocal_rank(ranked, {A1}, 5) == 0.0
    assert metrics.reciprocal_rank(ranked, {A1}, 10) == pytest.approx(1 / 6)


def test_repeated_chunks_of_one_page_count_once() -> None:
    # Three chunks of the same relevant page: without dedup Recall would be 3 and nDCG > 1.
    ranked = [A1, A1, A1, B1]

    assert metrics.gains(ranked, {A1}) == [1, 0, 0, 0]
    assert metrics.recall_at_k(ranked, {A1}, 5) == 1.0
    assert metrics.ndcg_at_k(ranked, {A1}, 10) == pytest.approx(1.0)


def test_two_relevant_pages() -> None:
    ranked = [A1, B1, A3]

    assert metrics.recall_at_k(ranked, {A1, A3}, 2) == 0.5
    expected = (1 + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    assert metrics.ndcg_at_k(ranked, {A1, A3}, 10) == pytest.approx(expected)


def test_metrics_refuse_questions_without_relevant_pages() -> None:
    with pytest.raises(ValueError):
        metrics.recall_at_k([A1], set(), 5)


def test_auc() -> None:
    assert metrics.auc([90, 80], [10, 20]) == 1.0
    assert metrics.auc([10], [90]) == 0.0
    assert metrics.auc([50], [50]) == 0.5
    assert metrics.auc([50], []) is None


def test_bootstrap_ci_is_seeded_and_brackets_the_mean() -> None:
    values = [0.0, 1.0] * 20
    low, high = metrics.bootstrap_ci(values)

    assert (low, high) == metrics.bootstrap_ci(values)
    assert low < 0.5 < high


# ---------- dataset ----------

def _write_lines(path: Path, records: List[Dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def test_dataset_round_trip(tmp_path: Path) -> None:
    questions = [
        EvalQuestion("g-1", "What is BPTT?", "generated", (RelevantPage("a.pdf", 3),), "unrolled in time", 900),
        EvalQuestion("h-1", "bptt vs truncated bptt", "hard", (RelevantPage("a.pdf", 3), RelevantPage("a.pdf", 4)),
                     multi_part=True, paired_with="g-1"),
        EvalQuestion("n-1", "Who won the 1998 World Cup?", "negative", ()),
    ]
    path = tmp_path / "set.jsonl"
    write_questions(path, questions)

    assert load_questions(path) == questions


def test_dataset_rejects_a_dangling_pair(tmp_path: Path) -> None:
    record = {"id": "h-1", "question": "q", "type": "hard", "relevant": [{"file_name": "a.pdf", "page": 1}],
              "paired_with": "g-404"}
    with pytest.raises(DatasetError, match="paired_with"):
        load_questions(_write_lines(tmp_path / "pair.jsonl", [record]))


def test_problems_against_corpus() -> None:
    pages = {("a.pdf", 1): "Gradients  VANISH over\nlong sequences.", ("a.pdf", 2): "LSTM gates."}
    questions = [
        EvalQuestion("ok", "q", "generated", (RelevantPage("a.pdf", 1),), "gradients vanish over long"),
        EvalQuestion("other-page", "q", "hard", (RelevantPage("a.pdf", 1), RelevantPage("a.pdf", 2)), "lstm gates"),
        EvalQuestion("bad-quote", "q", "generated", (RelevantPage("a.pdf", 2),), "gradients vanish"),
        EvalQuestion("bad-page", "q", "generated", (RelevantPage("a.pdf", 9),), None),
        EvalQuestion("neg", "q", "negative", ()),
    ]

    assert problems_against_corpus(questions, pages) == [
        "bad-quote: evidence not found on its labelled page(s)",
        "bad-page: no page 9 in a.pdf",
    ]


@pytest.mark.parametrize(
    "record",
    [
        {"id": "x", "question": "q", "type": "generated", "relevant": []},
        {"id": "x", "question": "q", "type": "negative", "relevant": [{"file_name": "a.pdf", "page": 1}]},
        {"id": "x", "question": "q", "type": "easy", "relevant": [{"file_name": "a.pdf", "page": 1}]},
        {"id": "x", "question": "  ", "type": "hard", "relevant": [{"file_name": "a.pdf", "page": 1}]},
        {"id": "x", "type": "hard", "relevant": [{"file_name": "a.pdf", "page": 1}]},
    ],
)
def test_dataset_rejects_bad_records(tmp_path: Path, record: Dict[str, Any]) -> None:
    with pytest.raises(DatasetError):
        load_questions(_write_lines(tmp_path / "bad.jsonl", [record]))


def test_dataset_rejects_duplicate_ids(tmp_path: Path) -> None:
    record = {"id": "x", "question": "q", "type": "negative", "relevant": []}
    with pytest.raises(DatasetError, match="duplicate"):
        load_questions(_write_lines(tmp_path / "dup.jsonl", [record, record]))


# ---------- embedding cache ----------

class _FailingModels:
    def embed_content(self, **kwargs: Any) -> Any:
        raise QUOTA_ERROR


class _FailingClient:
    models = _FailingModels()


def test_cache_serves_repeats_without_api_calls(tmp_path: Path) -> None:
    cache_path = tmp_path / "e.sqlite"
    first = CachedEmbeddingService(FakeGenaiClient(), cache_path)  # type: ignore[arg-type]
    vectors = first.embed_texts(["alpha", "beta", "alpha"])
    first.close()

    second = CachedEmbeddingService(FakeGenaiClient(), cache_path)  # type: ignore[arg-type]
    again = second.embed_texts(["beta", "alpha"])

    assert first.api_calls == 2  # "alpha" twice in one batch is embedded once
    assert second.api_calls == 0 and second.hits == 2
    assert vectors.shape == (3, first.dimension)
    assert (again[0] == vectors[1]).all() and (again[1] == vectors[0]).all()
    second.close()


def test_a_failed_call_stops_the_run_and_caches_nothing(tmp_path: Path) -> None:
    cache_path = tmp_path / "e.sqlite"
    failing = CachedEmbeddingService(_FailingClient(), cache_path)  # type: ignore[arg-type]
    with pytest.raises(EmbeddingFailure):
        failing.embed_texts(["alpha"])
    failing.close()

    healthy = CachedEmbeddingService(FakeGenaiClient(), cache_path)  # type: ignore[arg-type]
    healthy.embed_texts(["alpha"])
    assert healthy.api_calls == 1  # nothing was cached by the failed run
    healthy.close()


class _FlakyModels:
    """Embeds `allowed` texts, then fails like a 429 (EmbeddingService raises EmbeddingError)."""

    def __init__(self, allowed: int) -> None:
        self.allowed = allowed
        self.calls = 0
        self._real = FakeGenaiClient().models

    def embed_content(self, **kwargs: Any) -> Any:
        self.calls += 1
        if self.calls > self.allowed:
            raise QUOTA_ERROR
        return self._real.embed_content(**kwargs)


def test_blank_text_is_refused_without_a_call(tmp_path: Path) -> None:
    # Day 15: indexing skips blank chunks (B10), so a blank text reaching the cache is a bug; it used
    # to get a zero vector, which document_chunks now refuses.
    service = CachedEmbeddingService(FakeGenaiClient(), tmp_path / "e.sqlite")  # type: ignore[arg-type]

    with pytest.raises(EmbeddingFailure, match="blank"):
        service.embed_texts(["alpha", "  \n"])

    assert service.api_calls == 0
    service.close()


def test_cache_keeps_vectors_paid_for_before_a_failure(tmp_path: Path) -> None:
    cache_path = tmp_path / "e.sqlite"
    flaky = types.SimpleNamespace(models=_FlakyModels(allowed=2))
    stopped = CachedEmbeddingService(flaky, cache_path)  # type: ignore[arg-type]
    with pytest.raises(EmbeddingFailure, match="re-run to resume"):
        stopped.embed_texts(["a", "b", "c", "d"])
    stopped.close()

    resumed = CachedEmbeddingService(FakeGenaiClient(), cache_path)  # type: ignore[arg-type]
    resumed.embed_texts(["a", "b", "c", "d"])
    assert resumed.api_calls == 2  # only "c" and "d"
    resumed.close()


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: List[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_rate_limiter_paces_requests_per_minute() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(3, clock=clock, sleep=clock.sleep)

    for _ in range(7):
        limiter.acquire()

    # 3 in the first window, 3 in the second, the 7th in the third.
    assert len(clock.slept) == 2
    assert clock.now == pytest.approx(120.1)


def test_rate_limiter_paces_tokens_per_minute() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(100, tokens_per_minute=1000, clock=clock, sleep=clock.sleep)

    for _ in range(3):
        limiter.acquire(400)  # the third would make 1200 > 1000 tokens in one minute

    assert len(clock.slept) == 1
    with pytest.raises(ValueError):
        limiter.acquire(1001)


def test_token_estimate_errs_high() -> None:
    assert estimate_tokens("x" * 1000) == 334  # real Gemini tokenisation is ~250 for English prose


def test_embedding_pacing_for_the_corpus_fits_the_free_tier() -> None:
    # 392 unique chunks of ≤ 1000 characters: the TPM ceiling, not RPM, sets the pace.
    per_minute = EMBEDDING_TPM // estimate_tokens("x" * 1000)
    assert per_minute < EMBEDDING_RPM
    assert math.ceil(392 / per_minute) <= 5  # minutes


# ---------- evidence ----------

def _chunk(chunk_id: str, page: int, text: str) -> Dict[str, Any]:
    return {"text": text, "metadata": {"id": chunk_id, "file_name": "a.pdf", "page_num": page, "source_type": "local"}}


@pytest.mark.parametrize(
    ("served_text", "context", "expected"),
    [
        ("the answer is here", [_chunk("c1", 1, "the answer is here")], "survived"),
        ("x" * 790 + " the answer is here", [_chunk("c1", 1, "x" * 790 + " the")], "truncated"),
        ("the answer is here", [_chunk("other", 2, "unrelated")], "dropped"),
        ("nothing useful", [_chunk("c1", 1, "nothing useful")], "not_retrieved"),
    ],
)
def test_evidence_status(served_text: str, context: List[Dict[str, Any]], expected: str) -> None:
    question = EvalQuestion("g-1", "q", "generated", (RelevantPage("a.pdf", 1),), "The answer   is here")
    served = [_chunk("c1", 1, served_text)]

    assert evidence_status(question, served, AssembledContext(context, 80.0, False)) == expected


def test_evidence_status_without_a_quote() -> None:
    question = EvalQuestion("h-1", "q", "hard", (RelevantPage("a.pdf", 1),), None)
    assert evidence_status(question, [], AssembledContext([], 0.0, False)) == "no_evidence"


# ---------- question generation filters ----------

CHUNK_TEXT = (
    "Backpropagation through time unrolls the recurrent network across time steps, so gradients are "
    "multiplied by the same weight matrix many times and can vanish or explode."
)


def _chunk_obj(text: str = CHUNK_TEXT) -> DocumentChunk:
    return DocumentChunk(id="c", text=text, file_name="a.pdf", page_num=3, chunk_index=0, doc_type="pdf",
                         subject_tags=None, extra_metadata={})


@pytest.mark.parametrize(
    ("question", "evidence", "reason_start"),
    [
        ("Why do RNN training signals shrink or blow up over long sequences?", "can vanish or explode", None),
        ("Why can gradients vanish or explode when backpropagation through time unrolls the recurrent network?",
         "can vanish or explode", "copies"),
        ("What does this slide say about RNN training signals over long sequences?", "can vanish or explode", "refers"),
        ("Why do RNN training signals shrink over long sequences?", "gradients always vanish", "evidence"),
        ("", "", "no substantive"),
    ],
)
def test_generated_question_review(question: str, evidence: str, reason_start: str | None) -> None:
    _, reason = review(_chunk_obj(), GeneratedQuestion(question=question, evidence=evidence, answer="a"))

    if reason_start is None:
        assert reason is None
    else:
        assert reason is not None and reason.startswith(reason_start)


def test_lexical_overlap_ignores_stopwords() -> None:
    assert lexical_overlap("What is the of and", CHUNK_TEXT) == 0.0
    assert lexical_overlap("recurrent network gradients", CHUNK_TEXT) == 1.0


def test_quotas_have_a_floor_and_a_ceiling() -> None:
    # big.pdf is 94% of the chunks; weighted alone it would get 56 of 60. The ceiling is 35% (21).
    assert quotas({"big.pdf": 200, "small.pptx": 10, "tiny.pdf": 3}, target=60) == {
        "big.pdf": 21, "small.pptx": 6, "tiny.pdf": 3,
    }


GOOD_REPLY = json.dumps({
    "question": "Why do RNN training signals shrink or blow up over long sequences?",
    "evidence": "can vanish or explode",
    "answer": "Repeated multiplication by the same weights.",
})


def _quota_error(quota_id: str) -> genai_errors.APIError:
    return genai_errors.APIError(429, {"error": {
        "code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded",
        "details": [{"violations": [{"quotaId": quota_id}]}],
    }})


class _ScriptedModels:
    """Answers `allowed` generate calls, then raises the daily-quota 429 the free tier sends."""

    def __init__(self, allowed: int) -> None:
        self.allowed = allowed
        self.calls = 0

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls += 1
        if self.calls > self.allowed:
            raise _quota_error("GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return types.SimpleNamespace(text=GOOD_REPLY)


class _ScriptedClient:
    def __init__(self, allowed: int) -> None:
        self.models = _ScriptedModels(allowed)


def test_daily_quota_is_told_apart_from_a_per_minute_limit() -> None:
    assert is_daily_quota(_quota_error("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    assert not is_daily_quota(_quota_error("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"))


def test_daily_quota_stops_at_once_keeps_progress_and_resumes(tmp_path: Path) -> None:
    chunks = {"a.pdf": [
        DocumentChunk(id=f"c{i}", text=CHUNK_TEXT, file_name="a.pdf", page_num=i + 1, chunk_index=0,
                      doc_type="pdf", subject_tags=None, extra_metadata={})
        for i in range(5)
    ]}
    progress_path = tmp_path / "set.progress.jsonl"

    first = _ScriptedClient(allowed=2)
    completed = run_generation(first, chunks, {"a.pdf": 4}, progress_path, seed=1)  # type: ignore[arg-type]

    assert completed is False
    assert first.models.calls == 3  # two answers, then the quota error, then no retries
    saved = load_progress(progress_path)
    assert [r.status for r in saved] == ["kept", "kept"]

    second = _ScriptedClient(allowed=100)
    assert run_generation(second, chunks, {"a.pdf": 4}, progress_path, seed=1) is True  # type: ignore[arg-type]

    resumed = load_progress(progress_path)
    assert second.models.calls == 2  # only the two missing questions
    assert len({r.key for r in resumed}) == 4  # no chunk was asked about twice


def test_key_guard(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("JWT_SECRET_KEY=x\nGEMINI_API_KEY=prod-key-ABCD\n", encoding="utf-8")

    assert_eval_key("eval-key-WXYZ", env_file)
    with pytest.raises(ProductionKeyError):
        assert_eval_key("prod-key-ABCD", env_file)
    with pytest.raises(ProductionKeyError, match="cannot confirm"):
        assert_eval_key("eval-key-WXYZ", tmp_path / "missing.env")


# ---------- end to end (fake embeddings, no network) ----------

def _corpus_dir(tmp_path: Path) -> Path:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    shutil.copy(SAMPLES / "samples.pdf", corpus_dir / "samples.pdf")
    write_manifest(corpus_dir)
    return corpus_dir


def test_manifest_detects_a_changed_file(tmp_path: Path) -> None:
    corpus_dir = _corpus_dir(tmp_path)
    files = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))["files"]
    (corpus_dir / "samples.pdf").write_bytes(b"%PDF-1.4 changed")

    with pytest.raises(CorpusError, match="changed"):
        verify_corpus([CorpusFile(**f) for f in files], corpus_dir)


def test_end_to_end_run_is_deterministic(tmp_path: Path) -> None:
    corpus_dir = _corpus_dir(tmp_path)
    cache_path = tmp_path / "e.sqlite"

    embeddings = CachedEmbeddingService(FakeGenaiClient(), cache_path)  # type: ignore[arg-type]
    corpus = index_corpus(embeddings, corpus_dir, SessionLocal)
    assert sum(corpus.chunk_counts.values()) > 0

    first_chunk = corpus.chunks[0]
    questions = [
        EvalQuestion(
            "g-1", first_chunk["text"][:200], "generated",
            (RelevantPage(first_chunk["file_name"], first_chunk["page_num"]),),
            " ".join(first_chunk["text"].split()[:6]),
        ),
        EvalQuestion(
            "h-1", first_chunk["text"][:120].lower(), "hard",
            (RelevantPage(first_chunk["file_name"], first_chunk["page_num"]),), paired_with="g-1",
        ),
        EvalQuestion("n-1", "Who won the 1998 football World Cup?", "negative", ()),
    ]
    assert problems_against_corpus(questions, corpus.page_texts()) == []
    dataset = tmp_path / "set.jsonl"
    write_questions(dataset, questions)

    first = run(CONFIGS["baseline"], corpus, questions, dataset)
    second = run(CONFIGS["baseline"], corpus, questions, dataset)
    embeddings.close()

    assert [q.served_pages for q in first.questions] == [q.served_pages for q in second.questions]
    assert first.summary == second.summary
    assert first.questions[0].web_in_top5 == 0
    assert first.questions[2].hit_at_5 is None and first.questions[2].recall_at_5 is None
    assert first.summary["confidence"]["negatives"]["questions"] == 1
    assert [(p["hard"], p["generated"]) for p in first.summary["pairs"]] == [("h-1", "g-1")]
    assert "Same page, different wording" in render_markdown(first)

    rerun = CachedEmbeddingService(FakeGenaiClient(), cache_path)  # type: ignore[arg-type]
    reindexed = index_corpus(rerun, corpus_dir, SessionLocal)
    assert rerun.api_calls == 0
    # The previous run's eval user (and with it its chunks) is replaced, not duplicated.
    assert reindexed.user_id != corpus.user_id
    assert reindexed.chunk_counts == corpus.chunk_counts == {"samples.pdf": len(reindexed.chunks)}
    rerun.close()

    paths = write_results(first, tmp_path / "results", label="test")
    assert [p.name.split("-", 3)[-1] for p in paths] == ["baseline-test.json", "baseline-test.md"]
    assert "# Retrieval eval — baseline" in render_markdown(first)
