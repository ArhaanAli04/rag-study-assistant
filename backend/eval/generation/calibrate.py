"""Judge calibration against blind reference labels, plus judge self-consistency (Day 12).

    python -m eval.generation.calibrate sample   # pick 20, answer them, write the blind labelling sheet
    python -m eval.generation.calibrate score    # judge each answer twice, compare with your labels

`sample` stratifies by question type × grounding band (at least 8 strict answers, since the gate's
headline is strict-band faithfulness), answers each question with the chat's own prompt, and
writes:
- datasets/generation_calibration_v1.sheet.md   (gitignored: question, the exact material the model
  was given, the answer — no judge output, so the labels are blind)
- datasets/generation_calibration_v1.labels.jsonl  (committed once filled: ids + labels only)

`score` judges every answer twice (replica 0 is the verdict the full run reuses, replica 1 an
independent second sample: 3.5 Flash-Lite runs at temperature 1.0), derives one label per
dimension from each verdict, and reports judge-vs-judge and judge-vs-reference agreement. Generator
and judge are the same model (2.5-flash-lite is not served to the new eval project), so the reference
labels are the only check on self-preference: every disagreement is listed by direction — the
judge more lenient than the reference labels, or stricter.
"""
import argparse
import datetime
import json
import logging
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.gemini import build_gemini_client
from eval.generation import metrics
from eval.generation.answer_cache import ResultCache
from eval.generation.citations import check_citations
from eval.generation.judge import (
    DEFAULT_JUDGE_MODEL,
    FAITHFULNESS_PROMPT_VERSION,
    FAITHFULNESS_PROMPTS,
    RELEVANCE_PROMPT_VERSION,
    TEMPERATURE_SETTING,
    FaithfulnessVerdict,
)
from eval.generation.runner import DEFAULT_MODE, EvalContext, build_context, generate_answer, prepare
from eval.retrieval.corpus import index_corpus
from eval.retrieval.dataset import EvalQuestion, load_questions
from eval.retrieval.embedding_cache import CachedEmbeddingService
from eval.retrieval.generate_questions import DailyQuotaExhausted
from eval.retrieval.key_guard import assert_eval_key
from eval.retrieval.rate_limit import EMBEDDING_RPM, EMBEDDING_TPM, RateLimiter
from eval.retrieval.runner import RESULTS_DIR, _git_state

logger = logging.getLogger("eval.generation")

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"
DATASET = DATASETS_DIR / "retrieval_v1.jsonl"
NAME = "generation_calibration_v1"
LABELS_PATH = DATASETS_DIR / f"{NAME}.labels.jsonl"
SHEET_PATH = DATASETS_DIR / f"{NAME}.sheet.md"
GENERATOR_MODEL = "gemini-3.5-flash-lite"
SEED = 12
# The owner asked a different model family to label blind, then adjudicates every disagreement.
DEFAULT_PROVENANCE = "Claude (claude-opus-5-5), blind; disagreements adjudicated by the owner"

# (question type, grounding band, how many). 10 strict answers: the gate's headline is strict faithfulness.
STRATA: Tuple[Tuple[str, str, int], ...] = (
    ("generated", "strict", 6), ("generated", "loose", 6),
    ("hard", "strict", 2), ("hard", "loose", 2),
    ("negative", "strict", 2), ("negative", "loose", 1), ("negative", "none", 1),
)

DIMENSIONS = ("faithfulness", "relevance", "citations")
# Allowed labels per dimension, and the severity order used to tell a lenient judge from a strict one.
# Labels outside the order ("no_claims", "refusal", "none") are compared, but a disagreement involving
# them has no direction.
LABELS: Dict[str, Tuple[str, ...]] = {
    "faithfulness": ("supported", "not_in_context", "contradicted", "no_claims"),
    "relevance": ("full", "partial", "off_topic", "refusal"),
    "citations": ("correct", "some_wrong", "none"),
}
# Least to most severe: the judge is "more lenient" when its label sits earlier than the reference label's.
SEVERITY: Dict[str, Tuple[str, ...]] = {
    "faithfulness": ("supported", "not_in_context", "contradicted"),
    "relevance": ("full", "partial", "off_topic"),
    "citations": ("correct", "some_wrong"),
}

# A dimension is trusted only if the judge agrees with itself AND with the reference labels.
SELF_AGREEMENT_MIN = 0.80
REFERENCE_KAPPA_MIN = 0.40
REFERENCE_AGREEMENT_MIN_WHEN_NO_KAPPA = 0.80


# ---------- labels from a verdict ----------

def faithfulness_label(verdict: FaithfulnessVerdict) -> str:
    """The answer's worst claim."""
    verdicts = {c.verdict for c in verdict.claims}
    if not verdicts:
        return "no_claims"
    if "contradicted" in verdicts:
        return "contradicted"
    if "not_in_context" in verdicts:
        return "not_in_context"
    return "supported"


def citations_label(verdict: FaithfulnessVerdict) -> str:
    cited = [c for c in verdict.claims if c.citation_supports != "no_citation"]
    if not cited:
        return "none"
    return "some_wrong" if any(c.citation_supports == "no" for c in cited) else "correct"


def direction(dimension: str, reference: str, judge: str) -> str:
    """'agree', 'lenient' (the judge is kinder than the reference label), 'stricter', or 'other'."""
    if reference == judge:
        return "agree"
    order = SEVERITY[dimension]
    if reference not in order or judge not in order:
        return "other"
    return "lenient" if order.index(judge) < order.index(reference) else "stricter"


# ---------- sampling ----------

def choose(bands: Dict[str, str], questions: Sequence[EvalQuestion], seed: int = SEED) -> Tuple[List[EvalQuestion], List[str]]:
    """The stratified sample, in dataset order, and a note for each stratum that came up short."""
    rng = random.Random(seed)
    chosen: List[EvalQuestion] = []
    shortfalls: List[str] = []
    for qtype, band, wanted in STRATA:
        pool = [q for q in questions if q.type == qtype and bands[q.id] == band]
        picked = rng.sample(pool, min(wanted, len(pool)))
        if len(picked) < wanted:
            shortfalls.append(f"{qtype}/{band}: {len(picked)} of {wanted}")
        chosen.extend(picked)
    order = {q.id: i for i, q in enumerate(questions)}
    return sorted(chosen, key=lambda q: order[q.id]), shortfalls


@dataclass
class LabelRow:
    id: str
    faithfulness: Optional[str] = None
    relevance: Optional[str] = None
    citations: Optional[str] = None
    note: str = ""


def load_labels(path: Path = LABELS_PATH) -> List[LabelRow]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(LabelRow(**json.loads(line)))
    return rows


def label_problems(rows: Sequence[LabelRow]) -> List[str]:
    problems = []
    for row in rows:
        for dimension in DIMENSIONS:
            value = getattr(row, dimension)
            if value not in LABELS[dimension]:
                problems.append(f"{row.id}: {dimension} = {value!r} (allowed: {', '.join(LABELS[dimension])})")
    return problems


SHEET_HEADER = """# Generation judge calibration — blind labelling sheet

{n} answers from `{model}`, mode `{mode}`. For each one, fill its line in
`{labels}` (one JSON object per answer, same order). Judge only against the
**material the model was given** below, not against what you know is true.

- `faithfulness` — the answer's worst claim:
  - `supported`: every factual claim is stated in, or follows directly from, the material
  - `not_in_context`: at least one claim is absent from the material (even if it's true), none contradicted
  - `contradicted`: at least one claim conflicts with the material
  - `no_claims`: the answer only declines, greets or talks about the material — nothing to check
- `relevance` — does it address what was asked (not: is it right)?
  `full` (every part) · `partial` (some parts, a related question, or buried in padding) · `off_topic` · `refusal` (declines / says it can't answer)
- `citations` — `correct` (every `[Source: …]` / `[Web: …]` points at a material block that supports its
  sentence) · `some_wrong` (at least one doesn't, or names a page that isn't in the material) · `none` (no citations)
- `note` — optional, one line on anything borderline.

Under `loose` / `none` grounding the model was *allowed* general knowledge: still label such claims
`not_in_context` — the report separates allowed from violating by band.

"""


def write_sheet(items: Sequence[Tuple[EvalQuestion, str, str, str]], mode: str) -> None:
    """items: (question, grounding band, material the model was given, answer)."""
    lines = [SHEET_HEADER.format(n=len(items), model=GENERATOR_MODEL, mode=mode, labels=LABELS_PATH.name)]
    for number, (question, band, material, answer) in enumerate(items, start=1):
        lines += [
            f"## {number}. {question.id} — {question.type}, {band} grounding",
            "",
            f"**Question:** {question.question}",
            "",
            "<details><summary>Material the model was given</summary>",
            "",
            "```text",
            material,
            "```",
            "",
            "</details>",
            "",
            "**Answer:**",
            "",
            answer,
            "",
            "---",
            "",
        ]
    SHEET_PATH.write_text("\n".join(lines), encoding="utf-8")


def sample(ctx: EvalContext, questions: Sequence[EvalQuestion]) -> None:
    if LABELS_PATH.exists() and any(getattr(r, d) for r in load_labels() for d in DIMENSIONS):
        raise SystemExit(f"{LABELS_PATH.name} already holds labels; move it away before re-sampling")
    bands = {q.id: prepare(ctx, q).grounding_level for q in questions}
    chosen, shortfalls = choose(bands, questions)
    for note in shortfalls:
        logger.warning("stratum short: %s", note)
    items = []
    for number, question in enumerate(chosen, start=1):
        prepared = prepare(ctx, question)
        answer = generate_answer(ctx, prepared.prompt)
        items.append((question, prepared.grounding_level, prepared.prompt["current_user_text"], answer))
        logger.info("[%d/%d] %s %s answered", number, len(chosen), question.id, prepared.grounding_level)
    write_sheet(items, ctx.mode)
    with LABELS_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        for question, *_ in items:
            handle.write(json.dumps(asdict(LabelRow(question.id)), ensure_ascii=False) + "\n")
    logger.info("wrote %s and %s (%d strict)", SHEET_PATH, LABELS_PATH, sum(1 for _, b, _, _ in items if b == "strict"))


# ---------- scoring ----------

@dataclass
class ScoredItem:
    id: str
    type: str
    grounding: str
    reference: Dict[str, str]
    judge: Dict[str, str]
    judge_replica: Dict[str, str]
    code_fabricated_citations: int


def _agreement(a: Sequence[str], b: Sequence[str], dimension: str) -> Dict[str, Any]:
    order = SEVERITY[dimension]
    ordinal = [(x, y) for x, y in zip(a, b) if x in order and y in order]
    return {
        "n": len(a),
        "agreement": metrics.percent_agreement(a, b),
        "kappa": metrics.cohen_kappa(a, b),
        "weighted_kappa": metrics.weighted_kappa([x for x, _ in ordinal], [y for _, y in ordinal], order) if ordinal else None,
        "weighted_n": len(ordinal),
    }


def summarize(items: Sequence[ScoredItem]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for dimension in DIMENSIONS:
        reference = [i.reference[dimension] for i in items]
        judge = [i.judge[dimension] for i in items]
        replica = [i.judge_replica[dimension] for i in items]
        self_agreement = _agreement(judge, replica, dimension)
        reference_agreement = _agreement(reference, judge, dimension)
        kappa = reference_agreement["kappa"]
        reference_ok = (kappa is not None and kappa >= REFERENCE_KAPPA_MIN) or (
            kappa is None and (reference_agreement["agreement"] or 0) >= REFERENCE_AGREEMENT_MIN_WHEN_NO_KAPPA
        )
        directions: Dict[str, List[Tuple[str, str, str]]] = {"lenient": [], "stricter": [], "other": []}
        for item in items:
            d = direction(dimension, item.reference[dimension], item.judge[dimension])
            if d != "agree":
                directions[d].append((item.id, item.reference[dimension], item.judge[dimension]))
        summary[dimension] = {
            "judge_vs_judge": self_agreement,
            "judge_vs_reference": reference_agreement,
            "trusted": bool((self_agreement["agreement"] or 0) >= SELF_AGREEMENT_MIN and reference_ok),
            "reference_distribution": {label: reference.count(label) for label in LABELS[dimension]},
            "judge_distribution": {label: judge.count(label) for label in LABELS[dimension]},
            "disagreements": directions,
        }
    return summary


def score(ctx: EvalContext, questions: Sequence[EvalQuestion]) -> Tuple[List[ScoredItem], Dict[str, Dict[str, Any]]]:
    rows = load_labels()
    problems = label_problems(rows)
    if problems:
        raise SystemExit("labels are incomplete or invalid:\n  " + "\n  ".join(problems))
    by_id = {q.id: q for q in questions}
    items: List[ScoredItem] = []
    for number, row in enumerate(rows, start=1):
        question = by_id[row.id]
        prepared = prepare(ctx, question)
        answer = generate_answer(ctx, prepared.prompt)  # cached by `sample`
        material = prepared.prompt["current_user_text"]
        judged: List[Dict[str, str]] = []
        for replica in (0, 1):
            faith = ctx.judge.faithfulness(material, answer, replica=replica)
            relevance = ctx.judge.relevance(question.question, answer, replica=replica)
            judged.append({
                "faithfulness": faithfulness_label(faith),
                "relevance": relevance.label,
                "citations": citations_label(faith),
            })
        items.append(ScoredItem(
            id=row.id, type=question.type, grounding=prepared.grounding_level,
            reference={d: str(getattr(row, d)) for d in DIMENSIONS}, judge=judged[0], judge_replica=judged[1],
            code_fabricated_citations=check_citations(answer, prepared.context.chunks).fabricated,
        ))
        logger.info("[%d/%d] %s judged twice", number, len(rows), row.id)
    return items, summarize(items)


def _fmt(value: object) -> str:
    return "–" if value is None else f"{value:.2f}" if isinstance(value, float) else str(value)


def render(items: Sequence[ScoredItem], summary: Dict[str, Dict[str, Any]], meta: Dict[str, Any]) -> str:
    lines = [
        f"# Judge calibration — {meta['judge']} — {meta['date']}",
        "",
        f"{len(items)} answers from `{meta['generator']}` (mode `{meta['mode']}`), labelled blind (`{LABELS_PATH.name}`). "
        f"**Reference labels: {meta['provenance']}.** Each answer was judged twice by `{meta['judge']}` (prompts {meta['prompts']}, temperature "
        f"{meta['temperature']}). Commit `{meta['commit']}`. Generator and judge are the same model "
        "(gemini-2.5-flash-lite is not served to new projects), so the reference labels, from a different model "
        "family, are the only check on self-preference.",
        "",
        f"A dimension is **trusted** only if the judge agrees with itself (≥ {SELF_AGREEMENT_MIN:.2f}) and with the "
        f"reference labels (κ ≥ {REFERENCE_KAPPA_MIN:.2f}, or agreement ≥ {REFERENCE_AGREEMENT_MIN_WHEN_NO_KAPPA:.2f} when κ is "
        "undefined because one label covers everything). With 20 items κ's interval is wide: this separates "
        "usable from not, not 0.7 from 0.8.",
        "",
        "| Dimension | Judge vs judge: agreement / κ | Judge vs reference: agreement / κ / weighted κ (n) | Trusted |",
        "|---|---|---|---|",
    ]
    for dimension in DIMENSIONS:
        s = summary[dimension]
        jj, jo = s["judge_vs_judge"], s["judge_vs_reference"]
        lines.append(
            f"| {dimension} | {_fmt(jj['agreement'])} / {_fmt(jj['kappa'])} | "
            f"{_fmt(jo['agreement'])} / {_fmt(jo['kappa'])} / {_fmt(jo['weighted_kappa'])} ({jo['weighted_n']}) | "
            f"**{'yes' if s['trusted'] else 'no'}** |"
        )
    lines += ["", "## Label distributions — reference vs judge", ""]
    for dimension in DIMENSIONS:
        s = summary[dimension]
        lines.append(f"- **{dimension}** — reference {s['reference_distribution']}; judge {s['judge_distribution']}")
    for heading, key in (
        ("Judge MORE LENIENT than the reference labels (the self-preference risk)", "lenient"),
        ("Judge STRICTER than the reference labels", "stricter"),
        ("Other disagreements (no severity direction: no_claims / refusal / none involved)", "other"),
    ):
        lines += ["", f"## {heading}", ""]
        rows = [(d, case) for d in DIMENSIONS for case in summary[d]["disagreements"][key]]
        if not rows:
            lines.append("None.")
            continue
        lines += ["| Id | Dimension | Reference | Judge |", "|---|---|---|---|"]
        lines += [f"| {qid} | {d} | {reference} | {judge} |" for d, (qid, reference, judge) in rows]
    lines += [
        "",
        "## Per answer",
        "",
        "| Id | Type | Band | Faithfulness reference / judge / replica | Relevance reference / judge / replica | "
        "Citations reference / judge / replica | Fabricated (code) |",
        "|---|---|---|---|---|---|---|",
    ]
    for i in items:
        cells = [" / ".join((i.reference[d], i.judge[d], i.judge_replica[d])) for d in DIMENSIONS]
        lines.append(f"| {i.id} | {i.type} | {i.grounding} | " + " | ".join(cells) + f" | {i.code_fabricated_citations} |")
    lines.append("")
    return "\n".join(lines)


def _changed(old: Dict[str, Any], new: Dict[str, Any]) -> List[Tuple[str, str, str, str, str]]:
    """(id, dimension, reference, old judge/replica, new judge/replica) wherever a version changed a label."""
    old_items = {i["id"]: i for i in old["items"]}
    rows = []
    for item in new["items"]:
        before = old_items[item["id"]]
        for dimension in DIMENSIONS:
            was = (before["judge"][dimension], before["judge_replica"][dimension])
            now = (item["judge"][dimension], item["judge_replica"][dimension])
            if was != now:
                rows.append((item["id"], dimension, item["reference"][dimension], " / ".join(was), " / ".join(now)))
    return rows


def flips_against_supported(new: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """Answers the reference labels (owner-adjudicated) call supported / correct, that either pass
    of the new judge doesn't: these need the owner's eye before the new prompt becomes the baseline."""
    rows = []
    for item in new["items"]:
        for dimension, good in (("faithfulness", "supported"), ("citations", "correct")):
            if item["reference"][dimension] == good:
                passes = (item["judge"][dimension], item["judge_replica"][dimension])
                if any(p != good for p in passes):
                    rows.append((item["id"], dimension, " / ".join(passes)))
    return rows


def render_comparison(old: Dict[str, Any], new: Dict[str, Any]) -> str:
    old_v, new_v = old["meta"]["faithfulness_version"], new["meta"]["faithfulness_version"]
    lines = [
        f"# Judge calibration — {old_v} vs {new_v} — {new['meta']['date']}",
        "",
        f"Same {len(new['items'])} answers and reference labels ({new['meta']['provenance']}); relevance prompt unchanged. "
        f"**{new_v}'s agreement is optimistic: its rules were written after reading this set's disagreements, so it "
        "was tuned on the data it is scored on.** The full run is its first unseen test.",
        "",
        f"| Dimension | Judge vs judge {old_v} → {new_v} | Judge vs reference {old_v} → {new_v} (agreement / κ) | Trusted |",
        "|---|---|---|---|",
    ]
    for dimension in DIMENSIONS:
        a, b = old["summary"][dimension], new["summary"][dimension]
        lines.append(
            f"| {dimension} | {_fmt(a['judge_vs_judge']['agreement'])} → {_fmt(b['judge_vs_judge']['agreement'])} | "
            f"{_fmt(a['judge_vs_reference']['agreement'])} / {_fmt(a['judge_vs_reference']['kappa'])} → "
            f"{_fmt(b['judge_vs_reference']['agreement'])} / {_fmt(b['judge_vs_reference']['kappa'])} | "
            f"{'yes' if a['trusted'] else 'no'} → {'yes' if b['trusted'] else 'no'} |"
        )
    changed = _changed(old, new)
    lines += ["", f"## Labels {new_v} changed (judge / replica)", ""]
    if changed:
        lines += ["| Id | Dimension | Reference | " + old_v + " | " + new_v + " |", "|---|---|---|---|---|"]
        lines += [f"| {qid} | {d} | {ref} | {was} | {now} |" for qid, d, ref, was, now in changed]
    else:
        lines.append("None.")
    flips = flips_against_supported(new)
    lines += ["", f"## {new_v} disagrees with an adjudicated supported / correct label", ""]
    if flips:
        lines += ["| Id | Dimension | Judge / replica |", "|---|---|---|"]
        lines += [f"| {qid} | {d} | {passes} |" for qid, d, passes in flips]
    else:
        lines.append("None: no answer ruled supported (or correct) was marked otherwise by either pass.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m eval.generation.calibrate")
    parser.add_argument("step", choices=["sample", "score", "compare"])
    parser.add_argument("files", nargs="*", type=Path, help="compare: the older and the newer score JSON")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--faith-version", default=FAITHFULNESS_PROMPT_VERSION, choices=sorted(FAITHFULNESS_PROMPTS))
    parser.add_argument("--mode", default=DEFAULT_MODE)
    parser.add_argument("--provenance", default=DEFAULT_PROVENANCE, help="who made the reference labels, and how")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.step == "compare":
        if len(args.files) != 2:
            raise SystemExit("compare needs two score JSON files: older then newer")
        old, new = (json.loads(p.read_text(encoding="utf-8")) for p in args.files)
        out = RESULTS_DIR / (
            f"{new['meta']['date']}-calibration-{new['meta']['judge']}-"
            f"{old['meta']['faithfulness_version']}-vs-{new['meta']['faithfulness_version']}.md"
        )
        out.write_text(render_comparison(old, new), encoding="utf-8")
        logger.info("wrote %s", out)
        return

    assert_eval_key()
    client = build_gemini_client()
    questions = load_questions(DATASET)
    embeddings = CachedEmbeddingService(client, limiter=RateLimiter(EMBEDDING_RPM, EMBEDDING_TPM))
    cache = ResultCache()
    try:
        ctx = build_context(
            client, index_corpus(embeddings), cache, GENERATOR_MODEL, args.judge_model, args.mode, args.faith_version
        )
        if args.step == "sample":
            sample(ctx, questions)
            return
        items, summary = score(ctx, questions)
    except DailyQuotaExhausted as exc:
        raise SystemExit(f"{exc}; everything so far is cached — re-run after the reset") from exc
    finally:
        embeddings.close()
        cache.close()

    date = datetime.date.today().isoformat()
    meta = {
        "date": date, "generator": GENERATOR_MODEL, "mode": args.mode, "judge": args.judge_model,
        "prompts": f"{args.faith_version}, {RELEVANCE_PROMPT_VERSION}", "faithfulness_version": args.faith_version,
        "temperature": TEMPERATURE_SETTING, "commit": _git_state()["commit"], "provenance": args.provenance,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # Not Path.with_suffix: the ".5-flash-lite" in the model name would be taken for the extension.
    stem = f"{date}-calibration-{args.judge_model}-{args.faith_version}"
    (RESULTS_DIR / f"{stem}.json").write_text(json.dumps(
        {"meta": meta, "summary": summary, "items": [asdict(i) for i in items]}, indent=2, ensure_ascii=False
    ) + "\n", encoding="utf-8")
    (RESULTS_DIR / f"{stem}.md").write_text(render(items, summary, meta), encoding="utf-8")
    logger.info("wrote %s.{json,md}", RESULTS_DIR / stem)


if __name__ == "__main__":
    main()
