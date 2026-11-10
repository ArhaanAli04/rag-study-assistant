"""One-off: draft generated questions for a dataset version (Day 11, run from backend/).

    python -m eval.retrieval.generate_questions [--target 60] [--seed 11]

Samples chunks per corpus file, asks Gemini for one self-contained, paraphrased question per chunk
plus a verbatim evidence quote, and keeps a question only if:
- the quote really is in the chunk (else the label can't be trusted),
- it doesn't lean on the slide/document ("this slide", "the passage"…),
- at most MAX_OVERLAP of its content words appear in the chunk — copied wording would favour BM25.

Per-file quotas are weighted by eligible chunk count, with a floor (every file, and so both
parsers, is covered) and a ceiling (HPC Lecture.pptx holds over half the corpus and would
otherwise dominate the set).

Every attempt is appended to datasets/<name>.progress.jsonl as it happens (kept, or rejected with
its reason). A re-run skips chunks already kept or rejected, so a run stopped by the daily quota
resumes where it left off. Each run regenerates <name>.draft.jsonl (the dataset format) and
<name>.review.md (question, answer, quote and source side by side) from the progress file. Nothing
here is embedded, so it makes no embedding calls.
"""
import argparse
import json
import logging
import random
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set, Tuple

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError

from app.core.gemini import build_gemini_client
from app.ingestion.chunk_builder import build_chunks_from_pdf, build_chunks_from_pptx
from app.ingestion.models import DocumentChunk
from eval.retrieval.corpus import CORPUS_DIR, CorpusFile, load_manifest, verify_corpus
from eval.retrieval.dataset import EvalQuestion, RelevantPage, write_questions
from eval.retrieval.key_guard import assert_eval_key
from eval.retrieval.rate_limit import GENERATION_RPM, RateLimiter

logger = logging.getLogger("eval.generate")

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"
# The eval project's free tier allows gemini-2.5-flash and -flash-lite only 20 requests a day
# (Day 11's first run hit it); 3.5 / 3.1 Flash Lite allow 500. Fallback: --model gemini-3.1-flash-lite.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
MIN_CHUNK_CHARS = 200  # slide-PDF pages under this are titles or captions, not answerable content
MIN_PER_FILE = 6
MAX_SHARE = 0.35  # no file gets more than this share of the target
ATTEMPTS_PER_QUOTA = 3  # attempts per file stop at 3 × its quota, which bounds the API calls
MAX_OVERLAP = 0.5
MAX_RETRIES = 4

CONTEXT_DEPENDENT = re.compile(
    r"\b(this|the|that|above|following) (slide|document|passage|text|section|excerpt|page|figure|lecture|chunk)\b"
    r"|\baccording to\b|\bmentioned (here|above)\b",
    re.IGNORECASE,
)
STOPWORDS = frozenset(
    "the a an and or of to in on for with by from as at is are was were be been being what which who whom "
    "how why when where does do did can could would should will shall may might must this that these those "
    "it its into than then there their they them such not no yes also between about explain describe define "
    "role use used using give list main two three".split()
)

PROMPT = """You write exam-style study questions for evaluating a search engine over a student's course notes.

Read the passage and write ONE question that the passage answers.
Rules:
- Paraphrase. Do not copy phrases from the passage; use the wording a student would use when asking a tutor.
- Self-contained: never refer to "the passage", "this slide", "the document", "the lecture" or "the text".
- Answerable from this passage alone, about its substantive content (not page numbers, titles or authors).
- evidence: copy, character for character, the shortest span of the passage (one sentence or a phrase of
  5-30 words) that contains the answer.
- answer: one short sentence.
If the passage has no substantive content (a title slide, a table of contents, references), return an
empty question.

Passage (from {file_name}, page/slide {page}):
<<<
{text}
>>>"""

ChunkKey = Tuple[str, int, int]
Status = Literal["kept", "rejected", "failed"]


class DailyQuotaExhausted(RuntimeError):
    """A per-day quota resets at midnight Pacific time; retrying before then only burns time."""


class GeneratedQuestion(BaseModel):
    question: str
    evidence: str
    answer: str


@dataclass(frozen=True)
class ProgressRecord:
    file_name: str
    page: int
    chunk_index: int
    status: Status
    reason: Optional[str] = None
    question: Optional[str] = None
    evidence: Optional[str] = None
    answer: Optional[str] = None
    overlap: Optional[float] = None

    @property
    def key(self) -> ChunkKey:
        return (self.file_name, self.page, self.chunk_index)


def chunk_key(chunk: DocumentChunk) -> ChunkKey:
    return (chunk.file_name, int(chunk.page_num or 0), int(chunk.chunk_index))


# ---------- filters ----------

def _content_words(text: str) -> Set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOPWORDS}


def lexical_overlap(question: str, chunk_text: str) -> float:
    words = _content_words(question)
    if not words:
        return 0.0
    return len(words & _content_words(chunk_text)) / len(words)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def review(chunk: DocumentChunk, generated: GeneratedQuestion) -> tuple[float, Optional[str]]:
    overlap = lexical_overlap(generated.question, chunk.text)
    if not generated.question.strip():
        return overlap, "no substantive content (model returned an empty question)"
    if _normalize(generated.evidence) not in _normalize(chunk.text):
        return overlap, "evidence is not a verbatim span of the chunk"
    if CONTEXT_DEPENDENT.search(generated.question):
        return overlap, "refers to the slide/document"
    if overlap > MAX_OVERLAP:
        return overlap, f"copies the chunk's wording (overlap {overlap:.2f} > {MAX_OVERLAP})"
    return overlap, None


# ---------- sampling ----------

def load_chunks(files: List[CorpusFile]) -> Dict[str, List[DocumentChunk]]:
    builders = {".pdf": build_chunks_from_pdf, ".pptx": build_chunks_from_pptx}
    chunks: Dict[str, List[DocumentChunk]] = {}
    for f in files:
        build = builders[Path(f.file_name).suffix.lower()]
        all_chunks = build(str(CORPUS_DIR / f.file_name), document_id=f.document_id, file_name=f.file_name)
        chunks[f.file_name] = [c for c in all_chunks if len(c.text.strip()) >= MIN_CHUNK_CHARS and c.page_num]
        logger.info("%s: %d chunks, %d eligible", f.file_name, len(all_chunks), len(chunks[f.file_name]))
    return chunks


def quotas(eligible: Dict[str, int], target: int) -> Dict[str, int]:
    total = sum(eligible.values())
    ceiling = max(MIN_PER_FILE, round(target * MAX_SHARE))
    return {
        name: min(count, ceiling, max(MIN_PER_FILE, round(target * count / total)))
        for name, count in eligible.items()
    }


def max_attempts(quota: Dict[str, int], eligible: Dict[str, int]) -> int:
    """The most generation requests a full run can make (retries after a rate limit aside)."""
    return sum(min(eligible[name], ATTEMPTS_PER_QUOTA * q) for name, q in quota.items())


# ---------- generation ----------

def is_daily_quota(exc: genai_errors.APIError) -> bool:
    # The quota id (e.g. GenerateRequestsPerDayPerProjectPerModel-FreeTier) is in the error text;
    # a per-minute 429 names a PerMinute quota instead and is worth retrying.
    return exc.code == 429 and "PerDay" in str(exc)


def generate(
    client: genai.Client, chunk: DocumentChunk, model: str, limiter: Optional[RateLimiter] = None
) -> Optional[GeneratedQuestion]:
    config = genai_types.GenerateContentConfig(
        temperature=0.4,
        response_mime_type="application/json",
        response_schema=GeneratedQuestion,
    )
    prompt = PROMPT.format(file_name=chunk.file_name, page=chunk.page_num, text=chunk.text)
    for attempt in range(1, MAX_RETRIES + 1):
        if limiter is not None:
            limiter.acquire()
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config)
            return GeneratedQuestion.model_validate_json(response.text or "")
        except genai_errors.APIError as exc:
            if is_daily_quota(exc):
                raise DailyQuotaExhausted(f"{model} daily request quota exhausted") from exc
            if exc.code in (429, 500, 503) and attempt < MAX_RETRIES:
                wait = 15 * attempt
                logger.warning("Gemini %s on %s p%s, retrying in %ds", exc.code, chunk.file_name, chunk.page_num, wait)
                time.sleep(wait)
                continue
            logger.error("Gemini failed on %s p%s: %s", chunk.file_name, chunk.page_num, exc)
            return None
        except ValidationError as exc:
            logger.error("Malformed JSON for %s p%s: %s", chunk.file_name, chunk.page_num, exc)
            return None
    return None


# ---------- progress ----------

def load_progress(path: Path) -> List[ProgressRecord]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [ProgressRecord(**json.loads(line)) for line in handle if line.strip()]


def append_progress(path: Path, record: ProgressRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def run_generation(
    client: genai.Client,
    chunks: Dict[str, List[DocumentChunk]],
    quota: Dict[str, int],
    progress_path: Path,
    seed: int,
    model: str = DEFAULT_MODEL,
    limiter: Optional[RateLimiter] = None,
) -> bool:
    """Generate until every file meets its quota or its attempt cap. Returns False if the daily
    quota stopped the run; everything attempted so far is already in the progress file."""
    progress = load_progress(progress_path)
    settled = {r.key for r in progress if r.status in ("kept", "rejected")}
    for name, file_chunks in chunks.items():
        pool = list(file_chunks)
        random.Random(f"{seed}:{name}").shuffle(pool)  # per-file order, stable across resumes
        mine = [r for r in progress if r.file_name == name]
        kept = sum(1 for r in mine if r.status == "kept")
        attempts = sum(1 for r in mine if r.status in ("kept", "rejected"))
        cap = ATTEMPTS_PER_QUOTA * quota[name]
        for chunk in pool:
            if kept >= quota[name] or attempts >= cap:
                break
            if chunk_key(chunk) in settled:
                continue
            try:
                generated = generate(client, chunk, model, limiter)
            except DailyQuotaExhausted as exc:
                logger.error("%s: stopping; re-run after the quota resets to continue", exc)
                return False
            file_name, page, chunk_index = chunk_key(chunk)
            if generated is None:
                append_progress(progress_path, ProgressRecord(file_name, page, chunk_index, "failed", "generation failed"))
                continue
            overlap, reason = review(chunk, generated)
            record = ProgressRecord(
                file_name, page, chunk_index, "rejected" if reason else "kept", reason,
                generated.question.strip(), generated.evidence.strip(), generated.answer.strip(), round(overlap, 3),
            )
            append_progress(progress_path, record)
            attempts += 1
            kept += record.status == "kept"
        logger.info("%s: kept %d of quota %d (%d attempts)", name, kept, quota[name], attempts)
    return True


# ---------- outputs ----------

def render_outputs(name: str, progress: List[ProgressRecord], chunks: Dict[str, List[DocumentChunk]]) -> None:
    by_key = {chunk_key(c): c for file_chunks in chunks.values() for c in file_chunks}
    kept = [r for r in progress if r.status == "kept"]
    questions = [
        EvalQuestion(
            id=f"g-{n:03d}",
            question=r.question or "",
            type="generated",
            relevant=(RelevantPage(r.file_name, r.page),),
            evidence=r.evidence,
            source_chunk_chars=len(by_key[r.key].text) if r.key in by_key else None,
        )
        for n, r in enumerate(kept, start=1)
    ]
    write_questions(DATASETS_DIR / f"{name}.draft.jsonl", questions)

    reasons: Dict[str, int] = {}
    for r in progress:
        if r.status != "kept":
            label = (r.reason or "").split(" (")[0]
            reasons[label] = reasons.get(label, 0) + 1
    per_file: Dict[str, int] = {}
    for r in kept:
        per_file[r.file_name] = per_file.get(r.file_name, 0) + 1

    lines = [
        f"# {name} — draft review",
        "",
        f"{len(kept)} kept of {len(progress)} attempts. Not kept: "
        + (", ".join(f"{label} {count}" for label, count in sorted(reasons.items())) or "none")
        + f" (details in {name}.progress.jsonl).",
        "",
        "Kept per file: " + ", ".join(f"{f} {c}" for f, c in sorted(per_file.items())) + ".",
        "",
        "For each question: keep it, edit the wording, fix the page label, or delete its line in "
        f"`{name}.draft.jsonl`. Labels are the source page; add a page to `relevant` if the same answer "
        "is also on another page.",
        "",
    ]
    for question, record in zip(questions, kept):
        chunk = by_key.get(record.key)
        excerpt = " ".join(chunk.text.split()) if chunk else "(chunk not found in the current corpus)"
        lines += [
            f"## {question.id} — {record.file_name} p{record.page} (overlap {record.overlap:.2f})",
            "",
            f"**Q:** {record.question}  ",
            f"**A:** {record.answer}  ",
            f"**Evidence:** “{record.evidence}”",
            "",
            f"<details><summary>source chunk ({len(chunk.text) if chunk else 0} chars)</summary>\n\n{excerpt}\n\n</details>",
            "",
        ]
    (DATASETS_DIR / f"{name}.review.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m eval.retrieval.generate_questions")
    parser.add_argument("--name", default="retrieval_v1")
    parser.add_argument("--target", type=int, default=60)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--plan", action="store_true", help="print quotas and the request bound, call nothing")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    files = load_manifest()
    verify_corpus(files)
    chunks = load_chunks(files)
    eligible = {name: len(c) for name, c in chunks.items()}
    quota = quotas(eligible, args.target)
    progress_path = DATASETS_DIR / f"{args.name}.progress.jsonl"
    done = len([r for r in load_progress(progress_path) if r.status != "failed"])
    logger.info(
        "quotas %s (total %d); at most %d generation requests, %d already settled",
        quota, sum(quota.values()), max_attempts(quota, eligible), done,
    )
    if args.plan:
        return

    assert_eval_key()
    logger.info("model %s, paced at %d requests/minute", args.model, GENERATION_RPM)
    completed = run_generation(
        build_gemini_client(), chunks, quota, progress_path, args.seed,
        model=args.model, limiter=RateLimiter(GENERATION_RPM),
    )
    progress = load_progress(progress_path)
    render_outputs(args.name, progress, chunks)
    logger.info(
        "%s: %d kept, %d rejected, %d failed",
        "done" if completed else "stopped by the daily quota",
        sum(r.status == "kept" for r in progress),
        sum(r.status == "rejected" for r in progress),
        sum(r.status == "failed" for r in progress),
    )
    if not completed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
