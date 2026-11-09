"""Citation checks that need no model: is every citation in the answer one of the context labels the
model was actually shown?

The prompt (generation/llm_client.py) asks for `[Source: filename, Page X]` and `[Web: URL]`, and
labels each context chunk `Local file: {file_name}, Page {page_num or parent_page}` or
`Web URL: {url}`. A citation to a page that isn't among those labels is fabricated, whatever the
judge thinks of the sentence it is attached to.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple

CitationKind = Literal["local", "web"]

BRACKET = re.compile(r"\[\s*(Source|Web)\s*:\s*([^\]]*)\]", re.IGNORECASE)
PAGE_NUMBERS = re.compile(r"\bpages?\s*([0-9][0-9,\s\-–and&]*)", re.IGNORECASE)
PAGE_RANGE = re.compile(r"([0-9]+)\s*[-–]\s*([0-9]+)")


@dataclass(frozen=True)
class Citation:
    kind: CitationKind
    raw: str
    file_name: Optional[str] = None
    page: Optional[int] = None
    url: Optional[str] = None


@dataclass
class CitationReport:
    citations: List[Citation] = field(default_factory=list)
    valid: int = 0
    fabricated: int = 0
    malformed: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.valid + self.fabricated + len(self.malformed)


def _normalize_file(name: str) -> str:
    return " ".join(name.strip().strip("'\"`").lower().split())


def _normalize_url(url: str) -> str:
    return url.strip().strip("<>()").rstrip("/").lower()


def _pages(text: str) -> List[int]:
    match = PAGE_NUMBERS.search(text)
    if match is None:
        return []
    spec = match.group(1)
    pages: List[int] = []
    for low, high in PAGE_RANGE.findall(spec):
        start, end = int(low), int(high)
        # A range wider than this is a typo or a year, not pages someone checked.
        if 0 < end - start <= 10:
            pages.extend(range(start, end + 1))
    spec_without_ranges = PAGE_RANGE.sub(" ", spec)
    pages.extend(int(n) for n in re.findall(r"[0-9]+", spec_without_ranges))
    return sorted(set(pages))


def parse_citations(answer: str) -> Tuple[List[Citation], List[str]]:
    """Every citation in the answer, one per (file, page) or URL, plus the bracketed citations that
    name no page or URL (reported as malformed rather than guessed at)."""
    citations: List[Citation] = []
    malformed: List[str] = []
    for match in BRACKET.finditer(answer):
        kind, body = match.group(1).lower(), match.group(2)
        raw = match.group(0)
        if kind == "web":
            urls = [u for u in re.split(r"[\s;,]+", body) if u.lower().startswith("http")]
            if not urls:
                malformed.append(raw)
            citations.extend(Citation("web", raw, url=u) for u in urls)
            continue
        # One bracket may hold several sources: "[Source: a.pdf, Page 3; Source: b.pdf, Page 5]".
        for segment in re.split(r";|\bSource\s*:", body, flags=re.IGNORECASE):
            if not segment.strip():
                continue
            file_part = segment.split(",")[0]
            pages = _pages(segment)
            if not file_part.strip() or not pages or "page" in file_part.lower():
                malformed.append(raw)
                continue
            citations.extend(Citation("local", raw, file_name=file_part.strip(), page=p) for p in pages)
    return citations, malformed


def context_labels(context_chunks: Sequence[Dict[str, Any]]) -> Tuple[Set[Tuple[str, int]], Set[str]]:
    """The (file, page) pairs and URLs the model was shown, built exactly as build_prompt labels them."""
    pages: Set[Tuple[str, int]] = set()
    urls: Set[str] = set()
    for chunk in context_chunks:
        meta = chunk["metadata"]
        if meta.get("source_type", "local") == "web":
            urls.add(_normalize_url(str(meta.get("url", ""))))
            continue
        page = meta.get("page_num") or meta.get("parent_page")
        if page is not None:
            pages.add((_normalize_file(str(meta.get("file_name", ""))), int(page)))
    return pages, urls


def check_citations(answer: str, context_chunks: Sequence[Dict[str, Any]]) -> CitationReport:
    citations, malformed = parse_citations(answer)
    pages, urls = context_labels(context_chunks)
    report = CitationReport(citations=citations, malformed=malformed)
    for c in citations:
        if c.kind == "web":
            ok = _normalize_url(c.url or "") in urls
        else:
            ok = (_normalize_file(c.file_name or ""), int(c.page or 0)) in pages
        if ok:
            report.valid += 1
        else:
            report.fabricated += 1
    return report
