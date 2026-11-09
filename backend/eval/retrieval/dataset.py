"""The question set: one JSON object per line.

    {"id": "g-001", "question": "...", "type": "generated" | "hard" | "negative",
     "relevant": [{"file_name": "DL_Unit5_RNN.pdf", "page": 12}],
     "evidence": "verbatim quote from the page, or null", "source_chunk_chars": 987,
     "multi_part": false, "paired_with": null}

`multi_part` marks a question that asks two things (each answered on its own page), the case where
Recall@5 matters. `paired_with` links a hard (student-wording) question to the generated question
about the same page, so the summary can show what messy wording costs.

Labels are (document, page), never chunk ids, so a dataset survives re-chunking and re-indexing.
A released version (retrieval_v1.jsonl) is never edited in place; changes go into a new version so
old results stay comparable.
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Set, Tuple, cast

from eval.retrieval.metrics import PageKey

QuestionType = Literal["generated", "hard", "negative"]
QUESTION_TYPES: Tuple[QuestionType, ...] = ("generated", "hard", "negative")


class DatasetError(ValueError):
    pass


@dataclass(frozen=True)
class RelevantPage:
    file_name: str
    page: int


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    question: str
    type: QuestionType
    relevant: Tuple[RelevantPage, ...]
    evidence: Optional[str] = None
    source_chunk_chars: Optional[int] = None
    multi_part: bool = False
    paired_with: Optional[str] = None

    @property
    def relevant_keys(self) -> Set[PageKey]:
        return {(r.file_name, r.page) for r in self.relevant}

    @property
    def answerable(self) -> bool:
        return self.type != "negative"


def _parse(line_number: int, raw: dict) -> EvalQuestion:
    where = f"line {line_number}"
    try:
        question_type = raw["type"]
        relevant = tuple(RelevantPage(str(r["file_name"]), int(r["page"])) for r in raw["relevant"])
        question = EvalQuestion(
            id=str(raw["id"]),
            question=str(raw["question"]).strip(),
            type=cast(QuestionType, question_type),
            relevant=relevant,
            evidence=raw.get("evidence"),
            source_chunk_chars=raw.get("source_chunk_chars"),
            multi_part=bool(raw.get("multi_part", False)),
            paired_with=raw.get("paired_with"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DatasetError(f"{where}: malformed record ({exc})") from exc
    if question_type not in QUESTION_TYPES:
        raise DatasetError(f"{where}: unknown type {question_type!r}")
    if not question.question:
        raise DatasetError(f"{where}: empty question")
    if question.answerable and not question.relevant:
        raise DatasetError(f"{where}: {question_type} question without relevant pages")
    if not question.answerable and question.relevant:
        raise DatasetError(f"{where}: negative question must have no relevant pages")
    return question


def load_questions(path: Path) -> List[EvalQuestion]:
    questions: List[EvalQuestion] = []
    seen_ids: Set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"line {line_number}: invalid JSON ({exc})") from exc
            question = _parse(line_number, raw)
            if question.id in seen_ids:
                raise DatasetError(f"line {line_number}: duplicate id {question.id!r}")
            seen_ids.add(question.id)
            questions.append(question)
    if not questions:
        raise DatasetError(f"{path} holds no questions")
    dangling = [q.id for q in questions if q.paired_with is not None and q.paired_with not in seen_ids]
    if dangling:
        raise DatasetError(f"paired_with points at a missing id in: {', '.join(dangling)}")
    return questions


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def problems_against_corpus(questions: Iterable[EvalQuestion], page_texts: Dict[PageKey, str]) -> List[str]:
    """Labels that point at pages the corpus doesn't have, and evidence quotes not found on any of
    their question's labelled pages. Either means the results would be measured against a
    dataset that no longer matches the files."""
    problems: List[str] = []
    for q in questions:
        missing = [key for key in sorted(q.relevant_keys, key=str) if key not in page_texts]
        problems += [f"{q.id}: no page {page} in {file_name}" for file_name, page in missing]
        if q.evidence and not missing:
            quote = _normalize(q.evidence)
            if not any(quote in _normalize(page_texts[key]) for key in q.relevant_keys):
                problems.append(f"{q.id}: evidence not found on its labelled page(s)")
    return problems


def write_questions(path: Path, questions: Iterable[EvalQuestion]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for question in questions:
            record = asdict(question)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
