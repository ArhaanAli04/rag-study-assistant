"""Per question: the chat's own prepare_answer() over the eval corpus (web off, L1 off, production
top_k) → the answer from LLMClient.stream_answer, the call the chat streams → citation check →
the two judge calls. Then aggregates and writes results/{date}-generation-{model}[-label].{json,md}.

The Markdown summary holds ids and numbers only: answers, claims and quotes come from the
(private, gitignored) corpus, so they stay in the gitignored JSON.
"""
import datetime
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import fmean
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from google import genai

from app.generation.llm_client import LLMClient
from app.retrieval.context_compressor import SimpleContextCompressor
from app.retrieval.query_decomposer import QueryDecomposer
from app.retrieval.retrieval_service import RetrievalService
from app.services.answer_preparation import PreparedAnswer, prepare_answer
from eval.generation import metrics
from eval.generation.answer_cache import ResultCache, cache_key
from eval.generation.citations import check_citations
from eval.generation.judge import (
    FAITHFULNESS_PROMPT_VERSION,
    RELEVANCE_PROMPT_VERSION,
    TEMPERATURE_SETTING,
    Judge,
    JudgeFailure,
)
from eval.retrieval.configs import CONFIGS, SERVED_TOP_K
from eval.retrieval.corpus import EVAL_USER_ID, IndexedCorpus
from eval.retrieval.dataset import EvalQuestion
from eval.retrieval.generate_questions import DailyQuotaExhausted
from eval.retrieval.metrics import bootstrap_ci
from eval.retrieval.rate_limit import GENERATION_RPM, RateLimiter
from eval.retrieval.runner import RESULTS_DIR, _git_state, build_retrieval_service, page_key

logger = logging.getLogger("eval.generation")

DEFAULT_MODE = "quick"  # ChatInput.js's default, so what most students get
ANSWER_TEMPERATURE = "default (LLMClient sets none)"
ANSWER_ATTEMPTS = 4
# LLMClient's circuit breaker opens for 60 s after 3 failures in a row; the last wait outlasts it.
ANSWER_RETRY_WAITS = (20, 40, 70)

# Absolute gate (owner, Day 12), used when no paired comparison with 2.5-flash-lite is possible.
GATE_STRICT_FAITHFULNESS_MIN = 0.90
GATE_CONTRADICTED_RATE_MAX = 0.05
GATE_FULL_RELEVANCE_MIN = 0.80


@dataclass
class EvalContext:
    retrieval_service: RetrievalService
    llm_client: LLMClient
    judge: Judge
    cache: ResultCache
    generation_limiter: Optional[RateLimiter]
    mode: str = DEFAULT_MODE
    sleep: Callable[[float], None] = time.sleep


@dataclass
class QuestionResult:
    id: str
    type: str
    question: str
    multi_part: bool
    grounding: str
    confidence: float
    context_pages: List[str]
    context_hit: Optional[bool]
    answer: str
    faithfulness: Optional[float] = None
    claims: List[Dict[str, Any]] = field(default_factory=list)
    relevance: Optional[str] = None
    relevance_reason: str = ""
    citations: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


def build_context(
    client: genai.Client, corpus: IndexedCorpus, cache: ResultCache, model: str, judge_model: str, mode: str,
    faithfulness_version: str = FAITHFULNESS_PROMPT_VERSION,
) -> EvalContext:
    # One limiter per model: when the generator and the judge are the same model they share its
    # per-minute quota.
    limiters: Dict[str, RateLimiter] = {}
    for name in (model, judge_model):
        limiters.setdefault(name, RateLimiter(GENERATION_RPM))
    return EvalContext(
        retrieval_service=build_retrieval_service(CONFIGS["baseline"], corpus),
        llm_client=LLMClient(client, model),
        judge=Judge(client, cache, limiters[judge_model], judge_model, faithfulness_version=faithfulness_version),
        cache=cache,
        generation_limiter=limiters[model],
        mode=mode,
    )


def prepare(ctx: EvalContext, question: EvalQuestion) -> PreparedAnswer:
    """The chat's own retrieval → grounding → prompt for one question. No generation call."""
    return prepare_answer(
        ctx.retrieval_service, QueryDecomposer(), SimpleContextCompressor(), ctx.llm_client,
        query=question.question, user_id=EVAL_USER_ID, doc_version=0, top_k=SERVED_TOP_K,
        mode=ctx.mode, recent_messages=[],
    )


def generate_answer(ctx: EvalContext, prompt: Dict[str, Any]) -> str:
    """The streamed answer, joined. Cached by (model, mode, temperature setting, full prompt)."""
    key = cache_key({
        "kind": "answer", "model": ctx.llm_client.model_name, "mode": ctx.mode,
        "temperature": ANSWER_TEMPERATURE, "prompt": prompt,
    })
    cached = ctx.cache.get(key)
    if cached is not None:
        return str(json.loads(cached)["answer"])

    problem = ""
    for attempt in range(1, ANSWER_ATTEMPTS + 1):
        if ctx.generation_limiter is not None:
            ctx.generation_limiter.acquire()
        try:
            answer = "".join(ctx.llm_client.stream_answer(prompt))
        except RuntimeError as exc:
            # LLMClient wraps every API error in a RuntimeError; the quota id survives in its text.
            if "PerDay" in str(exc):
                raise DailyQuotaExhausted(f"{ctx.llm_client.model_name} daily request quota exhausted") from exc
            problem = str(exc)[:200]
        else:
            if answer.strip():
                ctx.cache.put(key, "answer", json.dumps({"answer": answer}, ensure_ascii=False))
                return answer
            problem = "empty answer"
        if attempt < ANSWER_ATTEMPTS:
            wait = ANSWER_RETRY_WAITS[min(attempt, len(ANSWER_RETRY_WAITS)) - 1]
            logger.warning("answer attempt %d failed (%s); retrying in %ds", attempt, problem, wait)
            ctx.sleep(wait)
    raise RuntimeError(f"no answer after {ANSWER_ATTEMPTS} attempts: {problem}")


def _context_page(chunk: Dict[str, Any]) -> str:
    meta = chunk["metadata"]
    if meta.get("source_type") == "web":
        return f"web:{meta.get('url', '')}"
    return f"{meta.get('file_name', '')} p{meta.get('page_num') or meta.get('parent_page')}"


def evaluate_question(ctx: EvalContext, question: EvalQuestion) -> QuestionResult:
    prepared = prepare(ctx, question)
    chunks = prepared.context.chunks
    context_keys = {page_key(c) for c in chunks} | {
        (c["metadata"].get("file_name", ""), c["metadata"].get("parent_page")) for c in chunks
    }
    result = QuestionResult(
        id=question.id, type=question.type, question=question.question, multi_part=question.multi_part,
        grounding=prepared.grounding_level, confidence=float(prepared.context.confidence),
        context_pages=[_context_page(c) for c in chunks],
        context_hit=bool(context_keys & question.relevant_keys) if question.answerable else None,
        answer="",
    )
    try:
        result.answer = generate_answer(ctx, prepared.prompt)
    except RuntimeError as exc:
        if isinstance(exc, DailyQuotaExhausted):
            raise
        result.error = f"generation: {exc}"
        return result

    report = check_citations(result.answer, chunks)
    result.citations = {
        "total": report.total, "valid": report.valid, "fabricated": report.fabricated, "malformed": len(report.malformed),
    }
    try:
        faith = ctx.judge.faithfulness(prepared.prompt["current_user_text"], result.answer)
        relevance = ctx.judge.relevance(question.question, result.answer)
    except JudgeFailure as exc:
        result.error = f"judge: {exc}"
        return result
    result.faithfulness = metrics.faithfulness_score(faith)
    result.claims = [c.model_dump() for c in faith.claims]
    result.relevance = relevance.label
    result.relevance_reason = relevance.reason
    return result


# ---------- aggregation ----------

def _mean_ci(values: Sequence[float]) -> Optional[Dict[str, Any]]:
    if not values:
        return None
    low, high = bootstrap_ci(values)
    return {"mean": fmean(values), "ci95": [low, high], "n": len(values)}


def _claims_of(rows: Sequence[QuestionResult]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in rows:
        for c in r.claims:
            counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
            counts["total"] = counts.get("total", 0) + 1
            if c["citation_supports"] != "no_citation":
                counts["cited"] = counts.get("cited", 0) + 1
                if c["citation_supports"] == "yes":
                    counts["cited_supported"] = counts.get("cited_supported", 0) + 1
    return counts


def _faithfulness_block(rows: Sequence[QuestionResult]) -> Dict[str, Any]:
    claims = _claims_of(rows)
    total = claims.get("total", 0)
    return {
        "faithfulness": _mean_ci([r.faithfulness for r in rows if r.faithfulness is not None]),
        "claims": claims,
        "contradicted_rate": metrics.rate(claims.get("contradicted", 0), total),
        "not_in_context_rate": metrics.rate(claims.get("not_in_context", 0), total),
    }


def _relevance_block(rows: Sequence[QuestionResult]) -> Dict[str, Any]:
    labels = [r.relevance for r in rows if r.relevance is not None]
    distribution = {label: labels.count(label) for label in ("full", "partial", "off_topic", "refusal")}
    return {"n": len(labels), "distribution": distribution, "full_rate": metrics.rate(distribution["full"], len(labels))}


def aggregate(rows: Sequence[QuestionResult]) -> Dict[str, Any]:
    judged = [r for r in rows if r.error is None]
    answerable = [r for r in judged if r.type != "negative"]
    negatives = [r for r in judged if r.type == "negative"]
    strict = [r for r in judged if r.grounding == "strict"]

    citation_totals = {k: sum(r.citations.get(k, 0) for r in judged) for k in ("total", "valid", "fabricated", "malformed")}
    cited_claims = _claims_of(judged)

    overall = _faithfulness_block(judged)
    strict_block = _faithfulness_block(strict)
    relevance_answerable = _relevance_block(answerable)
    strict_faith = strict_block["faithfulness"]
    gate = {
        "strict_faithfulness": strict_faith["mean"] if strict_faith else None,
        "strict_faithfulness_min": GATE_STRICT_FAITHFULNESS_MIN,
        "contradicted_rate": overall["contradicted_rate"],
        "contradicted_rate_max": GATE_CONTRADICTED_RATE_MAX,
        "full_relevance_answerable": relevance_answerable["full_rate"],
        "full_relevance_min": GATE_FULL_RELEVANCE_MIN,
    }
    gate["passes"] = (
        gate["strict_faithfulness"] is not None and gate["strict_faithfulness"] >= GATE_STRICT_FAITHFULNESS_MIN
        and gate["contradicted_rate"] is not None and gate["contradicted_rate"] <= GATE_CONTRADICTED_RATE_MAX
        and gate["full_relevance_answerable"] is not None and gate["full_relevance_answerable"] >= GATE_FULL_RELEVANCE_MIN
    )
    return {
        "questions": len(rows),
        "judged": len(judged),
        "errors": [{"id": r.id, "error": r.error} for r in rows if r.error is not None],
        "overall": overall,
        "by_grounding": {
            band: {"answers": len(b), **_faithfulness_block(b)}
            for band in metrics.GROUNDING_BANDS
            for b in [[r for r in judged if r.grounding == band]]
        },
        "by_context_hit": {
            label: {"answers": len(b), **_faithfulness_block(b), "relevance": _relevance_block(b)}
            for label, b in (
                ("relevant page in context", [r for r in answerable if r.context_hit]),
                ("no relevant page in context", [r for r in answerable if r.context_hit is False]),
            )
        },
        "relevance": {"answerable": relevance_answerable, "negatives": _relevance_block(negatives)},
        "abstention": {
            "answerable": metrics.rate(sum(r.relevance == "refusal" for r in answerable), len(answerable)),
            "negatives": metrics.rate(sum(r.relevance == "refusal" for r in negatives), len(negatives)),
            # The prompt asks for a refusal only under strict grounding; under loose / none it allows
            # general knowledge, so an out-of-corpus question answered there is not a failure.
            "negatives_by_grounding": {
                band: {"answers": len(b), "refusals": sum(r.relevance == "refusal" for r in b)}
                for band in metrics.GROUNDING_BANDS
                for b in [[r for r in negatives if r.grounding == band]]
            },
        },
        "citations": {
            **citation_totals,
            "answers_with_citations": sum(1 for r in judged if r.citations.get("total", 0) > 0),
            "valid_rate": metrics.rate(citation_totals["valid"], citation_totals["total"]),
            "judge_support_rate": metrics.rate(cited_claims.get("cited_supported", 0), cited_claims.get("cited", 0)),
        },
        "absolute_gate": gate,
    }


# ---------- run + write ----------

@dataclass
class RunResult:
    meta: Dict[str, Any]
    summary: Dict[str, Any]
    questions: List[QuestionResult]
    complete: bool


def run(ctx: EvalContext, questions: Sequence[EvalQuestion], meta: Dict[str, Any]) -> RunResult:
    rows: List[QuestionResult] = []
    complete = True
    for number, question in enumerate(questions, start=1):
        try:
            row = evaluate_question(ctx, question)
        except DailyQuotaExhausted as exc:
            logger.error("%s: stopping after %d questions; re-run after the reset to resume from the cache", exc, len(rows))
            complete = False
            break
        rows.append(row)
        logger.info(
            "[%d/%d] %s  %s  faith=%s  relevance=%s  citations %s/%s%s",
            number, len(questions), question.id, row.grounding,
            "–" if row.faithfulness is None else f"{row.faithfulness:.2f}", row.relevance,
            row.citations.get("valid", 0), row.citations.get("total", 0), f"  ERROR {row.error}" if row.error else "",
        )
    full_meta = {
        **meta,
        "date": datetime.date.today().isoformat(),
        "git": _git_state(),
        "generator": {"model": ctx.llm_client.model_name, "mode": ctx.mode, "temperature": ANSWER_TEMPERATURE},
        "judge": {
            "model": ctx.judge.model, "temperature": TEMPERATURE_SETTING,
            "prompts": {"faithfulness": ctx.judge.faithfulness_version, "relevance": RELEVANCE_PROMPT_VERSION},
        },
        "retrieval": f"baseline config (web off, L1 off), top_k={SERVED_TOP_K}",
        "complete": complete,
        "cache": {"hits": ctx.cache.hits, "misses": ctx.cache.misses},
        "judge_api_calls": ctx.judge.api_calls,
    }
    return RunResult(full_meta, aggregate(rows), rows, complete)


def _fmt(value: Optional[float], digits: int = 3) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def _ci(block: Optional[Dict[str, Any]]) -> str:
    if not block:
        return "–"
    low, high = block["ci95"]
    return f"{block['mean']:.3f} [{low:.2f}–{high:.2f}] (n={block['n']})"


def render_markdown(result: RunResult) -> str:
    s, m = result.summary, result.meta
    overall = s["overall"]
    claims = overall["claims"]
    lines = [
        f"# Generation eval — {m['generator']['model']} — {m['date']}",
        "",
        f"Dataset `{m['dataset']['path']}` ({m['dataset']['questions']} questions, sha256 "
        f"`{m['dataset']['sha256'][:12]}`), commit `{m['git']['commit']}`"
        f"{' (app/ or eval/ had uncommitted changes)' if m['git']['dirty'] else ''}. "
        f"Generator `{m['generator']['model']}`, mode `{m['generator']['mode']}`, temperature {m['generator']['temperature']}. "
        f"Judge `{m['judge']['model']}` (prompts {m['judge']['prompts']['faithfulness']}, "
        f"{m['judge']['prompts']['relevance']}), temperature {m['judge']['temperature']}. Retrieval: {m['retrieval']}. "
        f"Judged {s['judged']} of {s['questions']}{'' if m['complete'] else ' — INCOMPLETE (daily quota)'}.",
        "",
        "**How to read this.** Faithfulness = supported claims / all claims of an answer, judged against "
        "exactly the text the model was given; refusals have no claims and no score. `not_in_context` is "
        "allowed under `loose` and `none` grounding (the prompt permits general knowledge there) and is a "
        "violation under `strict`; `contradicted` is a bug under every band. Means with 95% bootstrap intervals.",
        "",
        "## Headline",
        "",
        "| Metric | Value |\n|---|---|",
        f"| Faithfulness, all scored answers | {_ci(overall['faithfulness'])} |",
        f"| Faithfulness, strict band | {_ci(s['by_grounding']['strict']['faithfulness'])} |",
        f"| Claims: supported / not_in_context / contradicted | {claims.get('supported', 0)} / "
        f"{claims.get('not_in_context', 0)} / {claims.get('contradicted', 0)} of {claims.get('total', 0)} |",
        f"| Contradicted-claim rate | {_fmt(overall['contradicted_rate'])} |",
        f"| Full relevance, answerable | {_fmt(s['relevance']['answerable']['full_rate'])} "
        f"(n={s['relevance']['answerable']['n']}) |",
        f"| Abstention: answerable / negatives | {_fmt(s['abstention']['answerable'])} / {_fmt(s['abstention']['negatives'])} |",
        f"| Citations: valid / fabricated / malformed | {s['citations']['valid']} / {s['citations']['fabricated']} / "
        f"{s['citations']['malformed']} (valid rate {_fmt(s['citations']['valid_rate'])}) |",
        f"| Answers with ≥1 citation | {s['citations']['answers_with_citations']} of {s['judged']} |",
        f"| Judge: cited claims the citation supports | {_fmt(s['citations']['judge_support_rate'])} |",
        "",
        "## By grounding band",
        "",
        "| Band | Answers | Faithfulness | not_in_context rate | Contradicted rate |\n|---|---|---|---|---|",
        *[
            f"| {band} | {b['answers']} | {_ci(b['faithfulness'])} | {_fmt(b['not_in_context_rate'])} | {_fmt(b['contradicted_rate'])} |"
            for band, b in s["by_grounding"].items()
        ],
        "",
        "## Retrieval → generation",
        "",
        "Answerable questions split by whether a labelled page reached the model's context (the E4 question, "
        "asked of the context the answer was generated from).",
        "",
        "| Context | Answers | Faithfulness | Full relevance |\n|---|---|---|---|",
        *[
            f"| {label} | {b['answers']} | {_ci(b['faithfulness'])} | {_fmt(b['relevance']['full_rate'])} |"
            for label, b in s["by_context_hit"].items()
        ],
        "",
        "## Relevance",
        "",
        f"Answerable: {s['relevance']['answerable']['distribution']}. Negatives: {s['relevance']['negatives']['distribution']}.",
        "",
        "Out-of-corpus negatives, refusals per grounding band (a refusal is asked for only under `strict`; "
        "`loose` / `none` allow a general-knowledge answer): "
        + ", ".join(
            f"{band} {b['refusals']}/{b['answers']}" for band, b in s["abstention"]["negatives_by_grounding"].items()
        )
        + ".",
        "",
    ]
    gate = s["absolute_gate"]
    lines += [
        "## Absolute gate (used when no paired comparison is possible)",
        "",
        f"Strict-band faithfulness {_fmt(gate['strict_faithfulness'])} (≥ {gate['strict_faithfulness_min']}), "
        f"contradicted-claim rate {_fmt(gate['contradicted_rate'])} (≤ {gate['contradicted_rate_max']}), "
        f"full relevance on answerable {_fmt(gate['full_relevance_answerable'])} (≥ {gate['full_relevance_min']}): "
        f"**{'pass' if gate['passes'] else 'fail'}**.",
        "",
        "## Per question",
        "",
        "| Id | Type | Band | Faithfulness | Claims (s/n/c) | Relevance | Citations valid/total |\n|---|---|---|---|---|---|---|",
    ]
    for r in result.questions:
        counts = {v: sum(1 for c in r.claims if c["verdict"] == v) for v in ("supported", "not_in_context", "contradicted")}
        lines.append(
            f"| {r.id} | {r.type} | {r.grounding} | {_fmt(r.faithfulness, 2)} | "
            f"{counts['supported']}/{counts['not_in_context']}/{counts['contradicted']} | {r.relevance or '–'} | "
            f"{r.citations.get('valid', 0)}/{r.citations.get('total', 0)}{' — ' + r.error if r.error else ''} |"
        )
    lines.append("")
    return "\n".join(lines)


class ResultsExist(FileExistsError):
    """A results file for this date, model and label is already there."""


def result_paths(results_dir: Path, date: str, model: str, label: Optional[str]) -> Tuple[Path, Path]:
    stem = f"{date}-generation-{model}" + (f"-{label}" if label else "")
    return results_dir / f"{stem}.json", results_dir / f"{stem}.md"


def refuse_existing(*paths: Path) -> None:
    existing = [p for p in paths if p.exists()]
    if existing:
        raise ResultsExist(
            f"{', '.join(p.name for p in existing)} already exist; pass --label for a separate file or --force to overwrite"
        )


def write_results(
    result: RunResult, results_dir: Path = RESULTS_DIR, label: Optional[str] = None, force: bool = False
) -> List[Path]:
    """Refuses to overwrite unless forced: a committed summary can carry hand-written sections (Day 12's
    baseline has the owner's review of h-02) that a re-run would silently erase."""
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = result_paths(results_dir, result.meta["date"], result.meta["generator"]["model"], label)
    if not force:
        refuse_existing(json_path, md_path)
    payload = {"meta": result.meta, "summary": result.summary, "questions": [asdict(q) for q in result.questions]}
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return [json_path, md_path]
