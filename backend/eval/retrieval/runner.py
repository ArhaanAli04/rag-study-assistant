"""Run one configuration over the question set and write results/{date}-{config}[-{label}].{json,md}.

Each question gets three calls on the same RetrievalService:
- served: hybrid_retrieve with production's parameters (top_k = rerank_top_k = 5). Recall@5, MRR@5,
  confidence and web share come from here, because this is what the chat sends the model.
- deep: top_k = rerank_top_k = 10 for Recall@10, MRR@10 and nDCG@10. Fetching 10 changes min-max
  normalization and confidence, so the deep pass's own top 5 is not reported.
- context: assemble_context(), the chat's own decompose → retrieve → expand → compress, to check
  whether the evidence quote survives into what the model reads.
"""
import datetime
import json
import logging
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import fmean, quantiles
from typing import Any, Dict, List, Literal, Optional, Sequence, Set

from app.retrieval import confidence as conf
from app.retrieval.context_assembly import RERANK_TOP_K, AssembledContext, assemble_context
from app.retrieval.context_compressor import SimpleContextCompressor
from app.retrieval.query_decomposer import QueryDecomposer
from app.retrieval.retrieval_service import RetrievalService
from eval.retrieval import metrics
from eval.retrieval.configs import DEEP_TOP_K, SERVED_TOP_K, RetrievalConfig
from eval.retrieval.corpus import EVAL_USER_ID, IndexedCorpus, sha256_of
from eval.retrieval.dataset import EvalQuestion
from eval.retrieval.metrics import PageKey

logger = logging.getLogger("eval.retrieval")

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
WEB_FLAT_SCORE = 0.5  # what hybrid_retrieve assigns every web chunk

EvidenceStatus = Literal["no_evidence", "not_retrieved", "survived", "truncated", "dropped"]


class NoQueryCache:
    """hybrid_retrieve never reads the query cache; semantic_search would, and must not here."""

    def get(self, user_id: str | None, query: str, doc_version: int) -> Optional[Any]:
        return None

    def set(self, user_id: str | None, query: str, doc_version: int, result: Any) -> None:
        return None


class MemoryWebCache:
    """In-process only, so the `web` config spends one Tavily search per question, not three."""

    def __init__(self) -> None:
        self._store: Dict[str, List[Dict[str, Any]]] = {}

    def get(self, query: str) -> Optional[List[Dict[str, Any]]]:
        return self._store.get(query)

    def set(self, query: str, results: List[Dict[str, Any]]) -> None:
        self._store[query] = results


def build_retrieval_service(config: RetrievalConfig, corpus: IndexedCorpus) -> RetrievalService:
    return RetrievalService(
        index_builder=corpus.index_builder,
        bm25_index=corpus.bm25_index,
        query_cache=NoQueryCache(),
        web_cache=MemoryWebCache(),
        web_search_enabled=config.web_search_enabled,
        l1_cache_enabled=False,
        vector_weight=config.vector_weight,
        keyword_weight=config.keyword_weight,
    )


def page_key(result: Dict[str, Any]) -> PageKey:
    meta = result["metadata"]
    if meta.get("source_type") == "web":
        return (f"web:{meta.get('url', '')}", None)
    return (meta.get("file_name", ""), meta.get("page_num"))


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def evidence_status(
    question: EvalQuestion, served_results: Sequence[Dict[str, Any]], context: AssembledContext
) -> EvidenceStatus:
    """Where the answer span ends up: in the model's context, cut off by the per-chunk character
    limit (its chunk is in the context, the quote isn't), dropped by the chunk-count limit, or
    never retrieved at all."""
    if not question.evidence:
        return "no_evidence"
    quote = _normalize(question.evidence)
    holders = [
        r for r in served_results
        if page_key(r) in question.relevant_keys and quote in _normalize(r.get("text", ""))
    ]
    if not holders:
        return "not_retrieved"
    if any(quote in _normalize(c.get("text", "")) for c in context.chunks):
        return "survived"
    context_ids = {c["metadata"].get("id") for c in context.chunks}
    if any(h["metadata"].get("id") in context_ids for h in holders):
        return "truncated"
    return "dropped"


@dataclass
class QuestionResult:
    id: str
    type: str
    question: str
    relevant: List[List[Any]]
    served_pages: List[List[Any]]
    deep_pages: List[List[Any]]
    multi_part: bool
    paired_with: Optional[str]
    first_relevant_rank_served: Optional[int]
    first_relevant_rank_deep: Optional[int]
    hit_at_5: Optional[float]
    recall_at_5: Optional[float]
    mrr_at_5: Optional[float]
    recall_at_10: Optional[float]
    mrr_at_10: Optional[float]
    ndcg_at_10: Optional[float]
    confidence: float
    grounding: str
    sub_queries: int
    evidence: str
    web_in_top5: int
    local_candidate_scores: List[float] = field(default_factory=list)


def _first_relevant_rank(ranked: Sequence[PageKey], relevant: Set[PageKey]) -> Optional[int]:
    return next((rank for rank, page in enumerate(ranked, start=1) if page in relevant), None)


def evaluate_question(service: RetrievalService, question: EvalQuestion) -> QuestionResult:
    served = service.hybrid_retrieve(
        question.question, EVAL_USER_ID, doc_version=0, top_k=SERVED_TOP_K, rerank_top_k=RERANK_TOP_K
    )
    deep = service.hybrid_retrieve(
        question.question, EVAL_USER_ID, doc_version=0, top_k=DEEP_TOP_K, rerank_top_k=DEEP_TOP_K
    )
    context = assemble_context(
        service, QueryDecomposer(), SimpleContextCompressor(),
        query=question.question, user_id=EVAL_USER_ID, doc_version=0, top_k=SERVED_TOP_K,
    )

    served_pages = [page_key(r) for r in served["results"]]
    deep_pages = [page_key(r) for r in deep["results"]]
    relevant = question.relevant_keys
    answerable = question.answerable

    return QuestionResult(
        id=question.id,
        type=question.type,
        question=question.question,
        relevant=[list(k) for k in sorted(relevant, key=str)],
        served_pages=[list(k) for k in served_pages],
        deep_pages=[list(k) for k in deep_pages],
        multi_part=question.multi_part,
        paired_with=question.paired_with,
        first_relevant_rank_served=_first_relevant_rank(served_pages, relevant),
        first_relevant_rank_deep=_first_relevant_rank(deep_pages, relevant),
        hit_at_5=metrics.hit_at_k(served_pages, relevant, SERVED_TOP_K) if answerable else None,
        recall_at_5=metrics.recall_at_k(served_pages, relevant, SERVED_TOP_K) if answerable else None,
        mrr_at_5=metrics.reciprocal_rank(served_pages, relevant, SERVED_TOP_K) if answerable else None,
        recall_at_10=metrics.recall_at_k(deep_pages, relevant, DEEP_TOP_K) if answerable else None,
        mrr_at_10=metrics.reciprocal_rank(deep_pages, relevant, DEEP_TOP_K) if answerable else None,
        ndcg_at_10=metrics.ndcg_at_k(deep_pages, relevant, DEEP_TOP_K) if answerable else None,
        confidence=float(served["confidence"]),
        grounding=conf.grounding_level(float(served["confidence"])),
        sub_queries=len(context.sub_queries),
        evidence=evidence_status(question, served["results"], context),
        web_in_top5=sum(1 for r in served["results"] if r["metadata"].get("source_type") == "web"),
        local_candidate_scores=[
            float(c["score"]) for c in served["all_candidates"] if c["metadata"].get("source_type") != "web"
        ],
    )


# ---------- aggregation ----------

def _metric_summary(values: Sequence[float]) -> Dict[str, Any]:
    low, high = metrics.bootstrap_ci(values)
    return {"mean": fmean(values), "ci95": [low, high], "n": len(values)}


METRIC_NAMES = ("hit_at_5", "mrr_at_5", "recall_at_5", "recall_at_10", "mrr_at_10", "ndcg_at_10")


def _ranking_block(rows: Sequence[QuestionResult]) -> Dict[str, Any]:
    block: Dict[str, Any] = {}
    for name in METRIC_NAMES:
        values = [getattr(r, name) for r in rows if getattr(r, name) is not None]
        if values:
            block[name] = _metric_summary(values)
    return block


def _pairs_block(rows: Sequence[QuestionResult]) -> List[Dict[str, Any]]:
    """Each hard (student-wording) question next to the generated question about the same page."""
    by_id = {r.id: r for r in rows}
    pairs = []
    for hard in rows:
        generated = by_id.get(hard.paired_with or "")
        if generated is None:
            continue
        pairs.append({
            "hard": hard.id, "generated": generated.id,
            "hard_hit_at_5": hard.hit_at_5, "generated_hit_at_5": generated.hit_at_5,
            "hard_rank_deep": hard.first_relevant_rank_deep, "generated_rank_deep": generated.first_relevant_rank_deep,
        })
    return pairs


def _confidence_block(rows: Sequence[QuestionResult]) -> Dict[str, Any]:
    answerable = [r for r in rows if r.hit_at_5 is not None]
    hit_scores = [r.confidence for r in answerable if r.hit_at_5]
    miss_scores = [r.confidence for r in answerable if not r.hit_at_5]
    bands: Dict[str, Dict[str, Any]] = {}
    for band in ("strict", "loose", "none"):
        in_band = [r for r in answerable if r.grounding == band]
        hits = sum(1 for r in in_band if r.hit_at_5)
        bands[band] = {"questions": len(in_band), "hit_at_5_rate": hits / len(in_band) if in_band else None}
    negatives = [r for r in rows if r.type == "negative"]
    return {
        "auc_hit_vs_miss": metrics.auc(hit_scores, miss_scores),
        "bands": bands,
        "negatives": {
            "questions": len(negatives),
            "mean_confidence": fmean([r.confidence for r in negatives]) if negatives else None,
            "max_confidence": max((r.confidence for r in negatives), default=None),
            "grounding": {b: sum(1 for r in negatives if r.grounding == b) for b in ("strict", "loose", "none")},
        },
    }


def _web_block(rows: Sequence[QuestionResult]) -> Dict[str, Any]:
    scores = sorted(s for r in rows for s in r.local_candidate_scores)
    if len(scores) >= 2:
        p25, p50, p75 = quantiles(scores, n=4)
        p90 = quantiles(scores, n=10)[-1]
    else:
        p25 = p50 = p75 = p90 = scores[0] if scores else 0.0
    return {
        "local_candidate_score_percentiles": {"p25": p25, "p50": p50, "p75": p75, "p90": p90},
        "local_candidates_below_web_score": (
            sum(1 for s in scores if s < WEB_FLAT_SCORE) / len(scores) if scores else None
        ),
        "web_share_of_top5": sum(r.web_in_top5 for r in rows) / (SERVED_TOP_K * len(rows)) if rows else None,
        "questions_with_web_in_top5": sum(1 for r in rows if r.web_in_top5),
    }


def aggregate(rows: Sequence[QuestionResult], by_document: Dict[str, List[QuestionResult]]) -> Dict[str, Any]:
    types = sorted({r.type for r in rows})
    evidence_counts: Dict[str, int] = {}
    for r in rows:
        if r.type != "negative":
            evidence_counts[r.evidence] = evidence_counts.get(r.evidence, 0) + 1
    return {
        "overall": _ranking_block(rows),
        "by_type": {t: _ranking_block([r for r in rows if r.type == t]) for t in types},
        "multi_part": _ranking_block([r for r in rows if r.multi_part]),
        "pairs": _pairs_block(rows),
        "by_document": {d: _ranking_block(rs) for d, rs in sorted(by_document.items())},
        "confidence": _confidence_block(rows),
        "evidence": evidence_counts,
        "web": _web_block(rows),
        "decomposed_questions": sum(1 for r in rows if r.sub_queries > 1),
    }


# ---------- run + write ----------

def _git_state() -> Dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "--", "app"], capture_output=True, text=True, check=True
        ).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unknown", "app_dirty": None}
    return {"commit": commit, "app_dirty": dirty}


@dataclass
class RunResult:
    config: RetrievalConfig
    meta: Dict[str, Any]
    summary: Dict[str, Any]
    questions: List[QuestionResult]


def run(
    config: RetrievalConfig, corpus: IndexedCorpus, questions: Sequence[EvalQuestion], dataset_path: Path
) -> RunResult:
    service = build_retrieval_service(config, corpus)
    rows: List[QuestionResult] = []
    by_document: Dict[str, List[QuestionResult]] = {}
    for number, question in enumerate(questions, start=1):
        row = evaluate_question(service, question)
        rows.append(row)
        if question.relevant:
            by_document.setdefault(question.relevant[0].file_name, []).append(row)
        logger.info("[%d/%d] %s  hit@5=%s  conf=%.1f", number, len(questions), question.id, row.hit_at_5, row.confidence)

    meta = {
        "date": datetime.date.today().isoformat(),
        "dataset": {"path": dataset_path.name, "sha256": sha256_of(dataset_path), "questions": len(questions)},
        "corpus": {
            "files": [{"file_name": f.file_name, "sha256": f.sha256} for f in corpus.files],
            "chunks": corpus.chunk_counts,
        },
        "git": _git_state(),
        "served_top_k": SERVED_TOP_K,
        "deep_top_k": DEEP_TOP_K,
    }
    return RunResult(config, meta, aggregate(rows, by_document), rows)


def _fmt(value: Optional[float], digits: int = 3) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def _metric_cell(block: Dict[str, Any], name: str) -> str:
    entry = block.get(name)
    if not entry:
        return "–"
    low, high = entry["ci95"]
    return f"{entry['mean']:.3f} [{low:.2f}–{high:.2f}]"


def render_markdown(result: RunResult) -> str:
    s = result.summary
    m = result.meta
    header = (
        "| Slice | n | **Hit@5** | **MRR@5** | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |\n"
        "|---|---|---|---|---|---|---|---|"
    )

    def row(label: str, block: Dict[str, Any]) -> str:
        n = block.get("hit_at_5", {}).get("n", 0)
        return f"| {label} | {n} | " + " | ".join(_metric_cell(block, k) for k in METRIC_NAMES) + " |"

    lines = [
        f"# Retrieval eval — {result.config.name} — {m['date']}",
        "",
        f"{result.config.description}. Dataset `{m['dataset']['path']}` ({m['dataset']['questions']} questions, "
        f"sha256 `{m['dataset']['sha256'][:12]}`), commit `{m['git']['commit']}`"
        f"{' (app/ had uncommitted changes)' if m['git']['app_dirty'] else ''}. "
        f"Served pass top_k={m['served_top_k']}, deep pass top_k={m['deep_top_k']}. "
        f"Embedding cache: {m.get('embedding_cache', {}).get('hits', 0)} hits, "
        f"{m.get('embedding_cache', {}).get('api_calls', 0)} API calls.",
        "",
        "**How to read this.** Means with 95% bootstrap intervals over questions.",
        "",
        "- **Hit@5** (any relevant page in the top 5) and **MRR@5** are the headline numbers. Both come from "
        "the served pass, exactly what the chat sends the model, and one answering page in that context is "
        "usually enough.",
        "- **Recall@5** matters only for two-part questions (the *two-part* row): each part is answered on "
        "its own page, so finding one half is a partial answer. A single-intent question with several "
        "answering pages (work stealing is explained on three HPC slides) should be judged on Hit@5, not "
        "Recall: one of the three is a full answer.",
        "- Recall@10, MRR@10 and nDCG@10 come from the deep pass (top 10) and show whether a miss was near.",
        "- Labels are (document, page) and may be incomplete: a fact repeated on an unlabelled page counts "
        "as a miss.",
        "",
        "## Ranking",
        "",
        header,
        row("all answerable", s["overall"]),
        *[row(f"type: {t}", b) for t, b in s["by_type"].items() if b],
        *([row("two-part questions", s["multi_part"])] if s["multi_part"] else []),
        *[row(f"doc: {d}", b) for d, b in s["by_document"].items()],
        "",
    ]
    pairs = s["pairs"]
    if pairs:
        hard_hits = sum(1 for p in pairs if p["hard_hit_at_5"])
        generated_hits = sum(1 for p in pairs if p["generated_hit_at_5"])
        lines += [
            "## Same page, different wording",
            "",
            f"Each student-wording (hard) question next to the generated question about the same page. "
            f"Hit@5: generated {generated_hits}/{len(pairs)}, student wording {hard_hits}/{len(pairs)}.",
            "",
            "| Hard | Generated | Hit@5 hard / generated | First relevant rank (top 10) hard / generated |\n"
            "|---|---|---|---|",
            *[
                f"| {p['hard']} | {p['generated']} | {_fmt(p['hard_hit_at_5'], 0)} / {_fmt(p['generated_hit_at_5'], 0)} "
                f"| {p['hard_rank_deep'] or '–'} / {p['generated_rank_deep'] or '–'} |"
                for p in pairs
            ],
            "",
        ]
    lines += [
        "## Does confidence predict a hit?",
        "",
        f"AUC (confidence of Hit@5 questions vs misses): **{_fmt(s['confidence']['auc_hit_vs_miss'])}** "
        "(0.5 = no signal, 1.0 = perfect separation).",
        "",
        "| Grounding band | Questions | Hit@5 rate |\n|---|---|---|",
        *[
            f"| {band} | {b['questions']} | {_fmt(b['hit_at_5_rate'])} |"
            for band, b in s["confidence"]["bands"].items()
        ],
        "",
    ]
    neg = s["confidence"]["negatives"]
    if neg["questions"]:
        lines += [
            f"Out-of-corpus negatives: {neg['questions']}, mean confidence {_fmt(neg['mean_confidence'], 1)}, "
            f"max {_fmt(neg['max_confidence'], 1)}; grounding {neg['grounding']}.",
            "",
        ]
    ev = s["evidence"]
    with_quote = sum(v for k, v in ev.items() if k != "no_evidence")
    lines += [
        "## Does compression cut answer spans?",
        "",
        f"Of {with_quote} answerable questions with an evidence quote: "
        + ", ".join(f"{k} {v}" for k, v in sorted(ev.items()) if k != "no_evidence")
        + ". `survived` = the quote is in the compressed context; `truncated` = its chunk was retrieved but the "
        "800-character cut removed it; `dropped` = its chunk lost to the 6-chunk limit; `not_retrieved` = no served "
        "chunk on a relevant page holds the quote.",
        "",
        "## Where does the flat 0.5 web score land?",
        "",
    ]
    web = s["web"]
    pct = web["local_candidate_score_percentiles"]
    lines += [
        f"Local candidates' hybrid scores: p25 {pct['p25']:.3f}, median {pct['p50']:.3f}, p75 {pct['p75']:.3f}, "
        f"p90 {pct['p90']:.3f}; {_fmt(web['local_candidates_below_web_score'])} of them score below 0.5.",
    ]
    if result.config.web_search_enabled:
        lines.append(
            f"Web chunks take {_fmt(web['web_share_of_top5'])} of the top-5 slots, in "
            f"{web['questions_with_web_in_top5']} of {len(result.questions)} questions."
        )
    else:
        lines.append("Web search is off in this config; run `--config web` for the slot share.")
    lines += [
        "",
        f"Questions the decomposer split into several sub-queries: {s['decomposed_questions']}.",
        "",
    ]
    return "\n".join(lines)


def write_results(result: RunResult, results_dir: Path = RESULTS_DIR, label: Optional[str] = None) -> List[Path]:
    results_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{result.meta['date']}-{result.config.name}" + (f"-{label}" if label else "")
    json_path = results_dir / f"{stem}.json"
    md_path = results_dir / f"{stem}.md"
    payload = {
        "config": asdict(result.config),
        "meta": result.meta,
        "summary": result.summary,
        "questions": [asdict(q) for q in result.questions],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return [json_path, md_path]
