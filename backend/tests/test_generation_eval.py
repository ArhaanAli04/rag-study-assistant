"""Day 12 (E1, E2): the generation eval's citation check, agreement statistics, judge client and
runner — offline, with scripted Gemini replies."""
import json
import types
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

import httpx
import pytest
from google.genai import errors as genai_errors

from app.generation.llm_client import LLMClient
from eval.generation import calibrate, metrics
from eval.generation import judge as judge_module
from eval.generation.answer_cache import ResultCache
from eval.generation.citations import check_citations, parse_citations
from eval.generation.judge import FaithfulnessVerdict, JudgedClaim, Judge, JudgeFailure
from eval.generation.runner import (
    EvalContext,
    QuestionResult,
    ResultsExist,
    RunResult,
    aggregate,
    evaluate_question,
    generate_answer,
    write_results,
)
from eval.retrieval.dataset import EvalQuestion, RelevantPage
from eval.retrieval.generate_questions import DailyQuotaExhausted
from tests.fakes import FakeGenaiClient

CHUNK_TEXT = "The forget gate decides which parts of the cell state to discard."


def _chunk(file_name: str = "DL_Unit5_RNN.pdf", page: Optional[int] = 78, parent_page: Optional[int] = None,
           url: Optional[str] = None) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"id": 1, "file_name": file_name, "page_num": page, "chunk_index": 0, "source_type": "local"}
    if parent_page is not None:
        meta["parent_page"] = parent_page
    if url is not None:
        meta = {"id": 2, "source_type": "web", "url": url}
    return {"text": CHUNK_TEXT, "score": 0.9, "metadata": meta}


# ---------- citations ----------

def test_both_citation_formats_and_multi_page_forms_are_parsed() -> None:
    answer = (
        "Gates control flow [Source: DL_Unit5_RNN.pdf, Page 78]. GRUs merge gates "
        "[Source: DL_Unit5_RNN.pdf, Pages 100-102; Source: notes.pdf, Page 3 and 5] [Web: https://en.wikipedia.org/wiki/LSTM]"
    )
    citations, malformed = parse_citations(answer)

    local = [(c.file_name, c.page) for c in citations if c.kind == "local"]
    assert local == [
        ("DL_Unit5_RNN.pdf", 78), ("DL_Unit5_RNN.pdf", 100), ("DL_Unit5_RNN.pdf", 101),
        ("DL_Unit5_RNN.pdf", 102), ("notes.pdf", 3), ("notes.pdf", 5),
    ]
    assert [c.url for c in citations if c.kind == "web"] == ["https://en.wikipedia.org/wiki/LSTM"]
    assert malformed == []


def test_a_file_name_with_commas_is_kept_whole() -> None:
    # Day 12 calibration: "BCT mod2,3,6.pdf" was cut at the first comma and valid citations
    # counted as fabricated.
    context = [_chunk(file_name="BCT mod2,3,6.pdf", page=23)]
    report = check_citations("UTXO model [Source: BCT mod2,3,6.pdf, Page 23].", context)

    assert [(c.file_name, c.page) for c in report.citations] == [("BCT mod2,3,6.pdf", 23)]
    assert (report.valid, report.fabricated) == (1, 0)


def test_a_citation_without_a_page_is_malformed_not_guessed() -> None:
    _, malformed = parse_citations("Something [Source: DL_Unit5_RNN.pdf].")
    assert malformed == ["[Source: DL_Unit5_RNN.pdf]"]


def test_validity_uses_the_labels_build_prompt_shows_including_parent_page() -> None:
    context = [_chunk(page=None, parent_page=12), _chunk(file_name="HPC Lecture.pptx", page=40),
               _chunk(url="https://en.wikipedia.org/wiki/LSTM/")]
    answer = (
        "[Source: DL_Unit5_RNN.pdf, Page 12] [Source: hpc lecture.pptx, Page 40] "
        "[Source: DL_Unit5_RNN.pdf, Page 13] [Web: https://en.wikipedia.org/wiki/LSTM]"
    )

    report = check_citations(answer, context)

    assert (report.valid, report.fabricated, report.total) == (3, 1, 4)  # page 13 was never shown


# ---------- agreement statistics ----------

def test_cohen_kappa_on_a_hand_worked_table() -> None:
    # pₒ = 3/4; pₑ = (2·1 + 2·3)/16 = 1/2; κ = (0.75 − 0.5) / 0.5 = 0.5
    assert metrics.cohen_kappa(["y", "y", "n", "n"], ["y", "n", "n", "n"]) == pytest.approx(0.5)
    assert metrics.cohen_kappa(["y", "n"], ["y", "n"]) == pytest.approx(1.0)
    assert metrics.cohen_kappa(["y", "y"], ["y", "y"]) is None  # chance agreement is total


def test_weighted_kappa_gives_partial_credit_for_a_near_miss() -> None:
    # observed disagreement (0 + 0.5 + 0)/3 = 1/6; expected 4.5/9 = 1/2; κw = 1 − (1/6)/(1/2) = 2/3
    order = ["off_topic", "partial", "full"]
    assert metrics.weighted_kappa(["off_topic", "partial", "full"], ["off_topic", "full", "full"], order) == pytest.approx(2 / 3)


def test_paired_difference_keeps_pairs_and_its_sign() -> None:
    mean, (low, high) = metrics.paired_difference([0.9, 1.0, 0.8, 1.0], [0.7, 0.8, 0.8, 0.9])
    assert mean == pytest.approx(0.125)
    assert 0 <= low <= mean <= high


def test_faithfulness_is_supported_over_all_claims_and_none_for_a_refusal() -> None:
    def claim(verdict: str) -> JudgedClaim:
        return JudgedClaim(claim="x", evidence="", verdict=verdict, cited_source="", citation_supports="no_citation")  # type: ignore[arg-type]

    assert metrics.faithfulness_score(FaithfulnessVerdict(claims=[claim("supported"), claim("not_in_context")])) == 0.5
    assert metrics.faithfulness_score(FaithfulnessVerdict(claims=[])) is None


# ---------- the judge client ----------

FAITH_REPLY = json.dumps({"claims": [{
    "claim": "The forget gate discards parts of the cell state.", "evidence": CHUNK_TEXT,
    "verdict": "supported", "cited_source": "[Source: DL_Unit5_RNN.pdf, Page 78]", "citation_supports": "yes",
}]})
RELEVANCE_REPLY = json.dumps({"reason": "Answers the question directly.", "label": "full"})

Reply = Union[str, Exception]


def _quota_error(quota_id: str) -> genai_errors.APIError:
    return genai_errors.APIError(429, {"error": {
        "code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded",
        "details": [{"violations": [{"quotaId": quota_id}]}],
    }})


class _ScriptedModels:
    def __init__(self, replies: List[Reply], default: Optional[str] = None) -> None:
        self.replies = list(replies)
        self.default = default
        self.calls = 0

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls += 1
        reply: Reply = self.replies.pop(0) if self.replies else (self.default or "")
        if isinstance(reply, Exception):
            raise reply
        return types.SimpleNamespace(text=reply)


class _ScriptedClient:
    def __init__(self, replies: List[Reply], default: Optional[str] = None) -> None:
        self.models = _ScriptedModels(replies, default)


def _judge(tmp_path: Path, replies: List[Reply], default: Optional[str] = None) -> Judge:
    return Judge(_ScriptedClient(replies, default), ResultCache(tmp_path / "c.sqlite"), sleep=lambda _: None)  # type: ignore[arg-type]


def test_verdicts_are_cached_and_a_replica_is_a_separate_judgment(tmp_path: Path) -> None:
    judge = _judge(tmp_path, [RELEVANCE_REPLY, RELEVANCE_REPLY])

    assert judge.relevance("q", "a").label == "full"
    assert judge.relevance("q", "a").label == "full"
    assert judge.api_calls == 1  # the repeat came from the cache
    judge.relevance("q", "a", replica=1)
    assert judge.api_calls == 2  # self-consistency needs a second, independent call


def test_malformed_json_is_retried_then_reported(tmp_path: Path) -> None:
    assert _judge(tmp_path, ["not json", FAITH_REPLY]).faithfulness("m", "a").claims[0].verdict == "supported"

    with pytest.raises(JudgeFailure, match="malformed JSON"):
        _judge(tmp_path / "x", [], default='{"label": "maybe"}').relevance("q", "a")


def test_daily_quota_stops_the_judge_but_a_per_minute_limit_is_retried(tmp_path: Path) -> None:
    per_minute = _quota_error("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
    assert _judge(tmp_path, [per_minute, RELEVANCE_REPLY]).relevance("q", "a").label == "full"

    with pytest.raises(DailyQuotaExhausted):
        _judge(tmp_path / "x", [_quota_error("GenerateRequestsPerDayPerProjectPerModel-FreeTier")]).relevance("q", "a")


def test_a_dropped_connection_is_retried(tmp_path: Path) -> None:
    dropped = httpx.RemoteProtocolError("Server disconnected without sending a response.")
    assert _judge(tmp_path, [dropped, RELEVANCE_REPLY]).relevance("q", "a").label == "full"


# ---------- the runner ----------

class _StubRetrieval:
    def hybrid_retrieve(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        chunk = _chunk()
        return {"results": [chunk], "all_candidates": [chunk], "confidence": 85.0, "fallback_used": False}

    def expand_to_parent_context(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return []


QUESTION = EvalQuestion(
    id="g-1", question="What does an LSTM's forget gate do?", type="generated",
    relevant=(RelevantPage("DL_Unit5_RNN.pdf", 78),),
)


def _context(tmp_path: Path, judge_replies: List[Reply], llm: Optional[LLMClient] = None) -> EvalContext:
    cache = ResultCache(tmp_path / "c.sqlite")
    return EvalContext(
        retrieval_service=_StubRetrieval(),  # type: ignore[arg-type]
        llm_client=llm or LLMClient(FakeGenaiClient(), "fake-model"),
        judge=Judge(_ScriptedClient(judge_replies), cache, sleep=lambda _: None),  # type: ignore[arg-type]
        cache=cache,
        generation_limiter=None,
        sleep=lambda _: None,
    )


def test_a_question_runs_the_chat_prompt_and_both_judges_then_replays_from_cache(tmp_path: Path) -> None:
    FakeGenaiClient.gemini.reset()
    FakeGenaiClient.gemini.streams.append(["The forget gate discards old state ", "[Source: DL_Unit5_RNN.pdf, Page 78]."])
    ctx = _context(tmp_path, [FAITH_REPLY, RELEVANCE_REPLY])

    first = evaluate_question(ctx, QUESTION)

    assert (first.grounding, first.context_hit, first.error) == ("strict", True, None)
    assert first.citations == {"total": 1, "valid": 1, "fabricated": 0, "malformed": 0}
    assert (first.faithfulness, first.relevance) == (1.0, "full")
    # The judge saw the same final user turn the model answered, context labels included.
    assert FakeGenaiClient.gemini.stream_calls == 1

    second = evaluate_question(ctx, QUESTION)
    assert FakeGenaiClient.gemini.stream_calls == 1 and ctx.judge.api_calls == 2
    assert second.answer == first.answer and second.faithfulness == first.faithfulness

    summary = aggregate([first])
    assert summary["by_grounding"]["strict"]["faithfulness"]["mean"] == 1.0
    assert summary["citations"]["valid_rate"] == 1.0


def test_answers_without_claims_are_left_out_of_the_faithfulness_mean() -> None:
    def row(qid: str, faithfulness: Optional[float]) -> QuestionResult:
        return QuestionResult(id=qid, type="generated", question="q", multi_part=False, grounding="strict",
                              confidence=80.0, context_pages=[], context_hit=True, answer="a",
                              faithfulness=faithfulness, relevance="full")

    summary = aggregate([row("a", 0.5), row("refusal", None)])

    # Neither 1.0 (mean 0.75) nor 0.0 (mean 0.25): the claimless answer is not in the mean at all.
    assert summary["overall"]["faithfulness"]["mean"] == 0.5
    assert summary["overall"]["faithfulness"]["n"] == 1


# ---------- calibration ----------

def _claim(verdict: str, support: str = "no_citation") -> JudgedClaim:
    return JudgedClaim(claim="x", evidence="", verdict=verdict, cited_source="" if support == "no_citation" else "[S]",  # type: ignore[arg-type]
                       citation_supports=support)  # type: ignore[arg-type]


def test_an_answer_is_labelled_by_its_worst_claim_and_any_wrong_citation() -> None:
    verdict = FaithfulnessVerdict(claims=[_claim("supported", "yes"), _claim("not_in_context", "no")])

    assert calibrate.faithfulness_label(verdict) == "not_in_context"
    assert calibrate.faithfulness_label(FaithfulnessVerdict(claims=[_claim("contradicted"), _claim("not_in_context")])) == "contradicted"
    assert calibrate.faithfulness_label(FaithfulnessVerdict(claims=[])) == "no_claims"
    assert calibrate.citations_label(verdict) == "some_wrong"
    assert calibrate.citations_label(FaithfulnessVerdict(claims=[_claim("supported")])) == "none"


def test_disagreements_are_split_into_lenient_and_stricter() -> None:
    assert calibrate.direction("faithfulness", reference="contradicted", judge="supported") == "lenient"
    assert calibrate.direction("faithfulness", reference="supported", judge="not_in_context") == "stricter"
    assert calibrate.direction("relevance", reference="partial", judge="full") == "lenient"
    assert calibrate.direction("relevance", reference="refusal", judge="full") == "other"
    assert calibrate.direction("citations", reference="correct", judge="correct") == "agree"


def test_the_sample_is_stratified_and_reports_short_strata() -> None:
    questions = [
        EvalQuestion(id=f"{t[0]}-{i}", question="q", type=t,  # type: ignore[arg-type]
                     relevant=() if t == "negative" else (RelevantPage("a.pdf", 1),))
        for t in ("generated", "hard", "negative") for i in range(20)
    ]
    bands = {q.id: ("strict" if int(q.id.split("-")[1]) < 10 else "loose") for q in questions}

    chosen, shortfalls = calibrate.choose(bands, questions)

    assert sum(1 for q in chosen if bands[q.id] == "strict") == 10
    assert len(chosen) == 19 and shortfalls == ["negative/none: 0 of 1"]  # no "none" band in this pool
    assert calibrate.choose(bands, questions)[0] == chosen  # seeded


def test_a_dimension_is_trusted_only_if_the_judge_agrees_with_itself_and_the_owner() -> None:
    def item(qid: str, human: str, judge: str, replica: str) -> calibrate.ScoredItem:
        labels = {"relevance": "full", "citations": "correct"}
        return calibrate.ScoredItem(qid, "generated", "strict", {"faithfulness": human, **labels},
                                    {"faithfulness": judge, **labels}, {"faithfulness": replica, **labels}, 0)

    consistent = [item("a", "supported", "supported", "supported"), item("b", "contradicted", "contradicted", "contradicted"),
                  item("c", "contradicted", "supported", "supported")]
    summary = calibrate.summarize(consistent)
    assert summary["faithfulness"]["disagreements"]["lenient"] == [("c", "contradicted", "supported")]

    flaky = [item("a", "supported", "supported", "contradicted"), item("b", "contradicted", "contradicted", "supported"),
             item("c", "supported", "supported", "contradicted")]
    assert calibrate.summarize(flaky)["faithfulness"]["trusted"] is False  # agrees with the owner, not with itself
    assert calibrate.label_problems([calibrate.LabelRow("a", "supported", None, "maybe")]) == [
        "a: relevance = None (allowed: full, partial, off_topic, refusal)",
        "a: citations = 'maybe' (allowed: correct, some_wrong, none)",
    ]


def test_faith_v2_adds_only_the_two_adjudicated_rules_and_v1_is_unchanged() -> None:
    v1, v2 = judge_module.FAITHFULNESS_PROMPTS["faith-v1"], judge_module.FAITHFULNESS_PROMPTS["faith-v2"]

    # The .replace() that builds v2 must have matched: an unmatched replace would silently make v2 == v1.
    assert v2 != v1 and v2.startswith(v1.split("Two kinds")[0][:200])
    assert "scope shift" in v2 and '"first"' in v2 and "Intensifiers" in v2
    assert "scope shift" not in v1  # v1 is reproducible from the cache only if its text never changes
    with pytest.raises(ValueError, match="unknown faithfulness prompt"):
        Judge(_ScriptedClient([]), ResultCache(Path(":memory:")), faithfulness_version="faith-v9")  # type: ignore[arg-type]


def test_the_comparison_flags_a_new_prompt_that_overrules_an_adjudicated_supported_label() -> None:
    def item(qid: str, reference: str, judge: str, replica: str) -> Dict[str, Any]:
        rest = {"relevance": "full", "citations": "correct"}
        return {"id": qid, "reference": {"faithfulness": reference, **rest},
                "judge": {"faithfulness": judge, **rest}, "judge_replica": {"faithfulness": replica, **rest}}

    old = {"items": [item("a", "supported", "supported", "supported"), item("b", "not_in_context", "supported", "supported")]}
    new = {"items": [item("a", "supported", "supported", "not_in_context"), item("b", "not_in_context", "not_in_context", "not_in_context")]}

    assert calibrate.flips_against_supported(new) == [("a", "faithfulness", "supported / not_in_context")]
    assert [row[0] for row in calibrate._changed(old, new)] == ["a", "b"]


def test_results_are_not_overwritten_unless_forced(tmp_path: Path) -> None:
    # Day 12's baseline summary carries a hand-written owner review that a re-run must not erase.
    meta = {"date": "2026-11-10", "generator": {"model": "m", "mode": "quick", "temperature": "t"},
            "judge": {"model": "m", "temperature": "t", "prompts": {"faithfulness": "f", "relevance": "r"}},
            "dataset": {"path": "d", "sha256": "0" * 12, "questions": 0}, "git": {"commit": "c", "dirty": False},
            "retrieval": "r", "complete": True}
    result = RunResult(meta=meta, summary=aggregate([]), questions=[], complete=True)
    _, md_path = write_results(result, tmp_path)
    md_path.write_text("hand-written owner review", encoding="utf-8")

    with pytest.raises(ResultsExist):
        write_results(result, tmp_path)
    assert md_path.read_text(encoding="utf-8") == "hand-written owner review"
    write_results(result, tmp_path, force=True)
    assert md_path.read_text(encoding="utf-8") != "hand-written owner review"


class _FailingLLM:
    """stream_answer raises like LLMClient does: every API error wrapped in a RuntimeError."""

    model_name = "fake-model"

    def __init__(self, errors: List[str], answer: str = "An answer.") -> None:
        self.errors = list(errors)
        self.answer = answer
        self.calls = 0

    def stream_answer(self, prompt: Dict[str, Any]) -> Iterator[str]:
        self.calls += 1
        if self.errors:
            raise RuntimeError(f"Streaming LLM call failed: {self.errors.pop(0)}")
        yield self.answer


def test_answer_generation_retries_transient_errors_and_stops_on_the_daily_quota(tmp_path: Path) -> None:
    flaky = _FailingLLM(["503 UNAVAILABLE"])
    ctx = _context(tmp_path, [], llm=flaky)  # type: ignore[arg-type]
    assert generate_answer(ctx, {"current_user_text": "q"}) == "An answer."
    assert flaky.calls == 2

    exhausted = _FailingLLM(["429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier"] * 4)
    ctx = _context(tmp_path / "x", [], llm=exhausted)  # type: ignore[arg-type]
    with pytest.raises(DailyQuotaExhausted):
        generate_answer(ctx, {"current_user_text": "q"})
    assert exhausted.calls == 1
