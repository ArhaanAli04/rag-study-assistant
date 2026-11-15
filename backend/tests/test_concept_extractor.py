"""Node sources come from the numbered context blocks the model cites (Day 17, D1).

Until Day 17 a node without sources got the first retrieved source of its type (B4 made that a
string, not a list); a guess shown as a citation. Now a source is either a block that was in the
context or nothing. Storage round trips are covered too (a JSON array, legacy comma-joined rows).
"""
import json
from typing import Any, Dict, List

import pytest

from app.generation.concept_extractor import ConceptExtractor, Evidence
from app.services.concept_map_service import decode_sources, encode_sources
from tests.fakes import FakeGemini, FakeGenaiClient

WIKI = "https://en.wikipedia.org/wiki/Photosynthesis"


def _doc(file_name: str, page: int, text: str) -> Dict[str, Any]:
    return {"text": text, "metadata": {"file_name": file_name, "page_num": page, "source_type": "local"}}


RETRIEVAL: Dict[str, Any] = {
    "document_results": [
        _doc("biology_notes.pdf", 4, "Chlorophyll absorbs light. " * 4),
        _doc("biology_notes.pdf", 4, "The light reactions happen in the thylakoid. " * 3),
        _doc("week 3, plants.pdf", 2, "The Calvin cycle fixes carbon dioxide. " * 3),
    ],
    "web_results": [
        {"text": "Photosynthesis converts light energy. " * 3, "metadata": {"url": WIKI, "title": "Photosynthesis"}},
    ],
    "sources": {"document_sources": ["biology_notes.pdf", "week 3, plants.pdf"], "web_sources": [WIKI]},
    "confidence": 72.0,
}


@pytest.fixture
def extractor() -> ConceptExtractor:
    return ConceptExtractor(FakeGenaiClient(), "fake-model")


def test_the_context_numbers_each_block_with_file_and_page(extractor: ConceptExtractor) -> None:
    context, evidence = extractor.build_context(RETRIEVAL)

    assert "[D1] biology_notes.pdf — p. 4:" in context
    assert "[D3] week 3, plants.pdf — p. 2:" in context
    assert f"[W1] Photosynthesis ({WIKI}):" in context
    kind, label, _ = evidence.blocks["D3"]
    assert (kind, label) == ("document", "week 3, plants.pdf — p. 2")


@pytest.mark.parametrize(("cited", "expected"), [
    (["D1"], ("document", ["biology_notes.pdf — p. 4"])),
    (["D1", "D2"], ("document", ["biology_notes.pdf — p. 4"])),  # same page twice → one source
    (["[d3]", " W1 "], ("both", ["week 3, plants.pdf — p. 2", WIKI])),
    (["D9", "biology_notes.pdf", "Document 1"], ("unknown", [])),  # not in the context → dropped
    ("D1", ("unknown", [])),  # not a list
    (None, ("unknown", [])),
])
def test_cited_ids_resolve_to_blocks_and_unknown_ones_are_dropped(
    extractor: ConceptExtractor, cited: Any, expected: Any
) -> None:
    _, evidence = extractor.build_context(RETRIEVAL)

    assert evidence.resolve(cited) == expected


def test_sources_are_sorted_by_file_and_page_then_urls() -> None:
    # The model cites in any order; the node details read best in page order ("p. 2" before "p. 10").
    retrieval = {
        "document_results": [
            _doc("notes.pdf", 10, "Limiting factors. " * 10),
            _doc("notes.pdf", 3, "Calvin cycle. " * 10),
            _doc("notes.pdf", 2, "Light reactions. " * 10),
            _doc("atlas.pdf", 7, "Leaves. " * 10),
        ],
        "web_results": [{"text": "Web text. " * 10, "metadata": {"url": WIKI, "title": "Photosynthesis"}}],
    }
    _, evidence = ConceptExtractor(FakeGenaiClient(), "fake-model").build_context(retrieval)

    assert evidence.resolve(["W1", "D1", "D2", "D4", "D3"]) == ("both", [
        "atlas.pdf — p. 7", "notes.pdf — p. 2", "notes.pdf — p. 3", "notes.pdf — p. 10", WIKI,
    ])


def test_an_off_topic_reply_returns_no_nodes_and_the_flag(gemini: FakeGemini) -> None:
    gemini.replies.append(json.dumps({"topic": "French Revolution", "off_topic": True, "nodes": [], "edges": []}))

    result = ConceptExtractor(FakeGenaiClient(), "fake-model").extract_concepts_from_hybrid_sources(
        "French Revolution", RETRIEVAL
    )

    assert result["off_topic"] is True
    assert result["nodes"] == []


def test_a_page_less_chunk_is_labelled_by_file_name() -> None:
    evidence = Evidence()
    evidence.add("D1", "document", "slides.pptx")

    assert evidence.resolve(["D1"]) == ("document", ["slides.pptx"])


def test_extraction_attributes_sources_from_ids_and_never_guesses(gemini: FakeGemini) -> None:
    nodes: List[Dict[str, Any]] = [
        {"id": "chlorophyll", "label": "Chlorophyll", "definition": "A pigment.", "source_ids": ["D1"]},
        # The model claims a file that wasn't retrieved: before Day 17 this was shown as its source.
        {"id": "stroma", "label": "Stroma", "definition": "Fluid.", "source_ids": [], "sources": ["made_up.pdf"]},
    ]
    gemini.replies.append(json.dumps({"nodes": nodes, "edges": []}))

    result = ConceptExtractor(FakeGenaiClient(), "fake-model").extract_concepts_from_hybrid_sources(
        "Photosynthesis", RETRIEVAL
    )

    by_id = {n["id"]: n for n in result["nodes"]}
    assert (by_id["chlorophyll"]["source_type"], by_id["chlorophyll"]["sources"]) == (
        "document", ["biology_notes.pdf — p. 4"]
    )
    assert (by_id["stroma"]["source_type"], by_id["stroma"]["sources"]) == ("unknown", [])
    assert "source_ids" not in by_id["chlorophyll"]
    assert result["source_summary"]["document_sources"] == ["biology_notes.pdf", "week 3, plants.pdf"]


def test_sources_with_commas_survive_storage() -> None:
    sources = ["week 3, plants.pdf — p. 2", WIKI]

    assert decode_sources(encode_sources(sources)) == sources


@pytest.mark.parametrize(("stored", "expected"), [
    ("biology_notes.pdf,https://x.org/a", ["biology_notes.pdf", "https://x.org/a"]),  # saved before Day 17
    ("", []),
    (None, []),
])
def test_legacy_comma_joined_sources_still_read(stored: Any, expected: List[str]) -> None:
    assert decode_sources(stored) == expected
