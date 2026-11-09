"""B4: a node without sources gets the first retrieved source of its type — a string, never a list."""
from typing import Any, Dict, List

import pytest

from app.generation.concept_extractor import ConceptExtractor
from tests.fakes import FakeGenaiClient

WEB = ["https://en.wikipedia.org/wiki/Photosynthesis", "https://biology.stackexchange.com/q/1"]
DOCS = ["biology_notes.pdf", "chapter2.docx"]


def _retrieval(web: List[str], docs: List[str]) -> Dict[str, Any]:
    return {"sources": {"web_sources": web, "document_sources": docs}, "confidence": 70.0}


def _node(source_type: str, sources: List[str]) -> Dict[str, Any]:
    return {"id": "n1", "label": "Photosynthesis", "source_type": source_type, "sources": sources}


@pytest.fixture
def extractor() -> ConceptExtractor:
    return ConceptExtractor(FakeGenaiClient(), "fake-model")


@pytest.mark.parametrize(("source_type", "expected"), [("web", WEB[0]), ("document", DOCS[0])])
def test_empty_sources_fall_back_to_the_first_source_of_that_type(
    extractor: ConceptExtractor, source_type: str, expected: str
) -> None:
    concept_map = {"nodes": [_node(source_type, [])]}

    result = extractor._add_source_attribution(concept_map, _retrieval(WEB, DOCS))

    assert result["nodes"][0]["sources"] == [expected]
    # What concept_map_service stores: must be a plain comma-joined string.
    assert ",".join(result["nodes"][0]["sources"]) == expected


def test_existing_sources_are_kept(extractor: ConceptExtractor) -> None:
    concept_map = {"nodes": [_node("web", ["own-source.pdf"])]}

    result = extractor._add_source_attribution(concept_map, _retrieval(WEB, DOCS))

    assert result["nodes"][0]["sources"] == ["own-source.pdf"]


def test_no_retrieved_source_of_that_type_leaves_sources_empty(extractor: ConceptExtractor) -> None:
    concept_map = {"nodes": [_node("document", [])]}

    result = extractor._add_source_attribution(concept_map, _retrieval(WEB, []))

    assert result["nodes"][0]["sources"] == []
