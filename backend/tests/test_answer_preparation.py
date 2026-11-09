"""Day 12: prepare_answer is the one path from a question to the Gemini prompt, shared by the chat and
the generation eval. These pin what the chat did inline before the extraction."""
from typing import Any, Dict, List

import pytest

from app.generation.llm_client import LLMClient
from app.retrieval.context_compressor import SimpleContextCompressor
from app.retrieval.query_decomposer import QueryDecomposer
from app.services.answer_preparation import prepare_answer
from tests.fakes import FakeGenaiClient

QUESTION = "What does an LSTM's forget gate do?"
CHUNK_TEXT = "The forget gate decides which parts of the cell state to discard."


def _chunk() -> Dict[str, Any]:
    return {
        "text": CHUNK_TEXT,
        "score": 0.9,
        "metadata": {
            "id": 1, "document_id": 1, "file_name": "DL_Unit5_RNN.pdf", "page_num": 78,
            "chunk_index": 0, "source_type": "local", "user_id": "1",
        },
    }


class StubRetrieval:
    """Returns one chunk at a fixed confidence; records the sub-queries it was asked."""

    def __init__(self, confidence: float) -> None:
        self.confidence = confidence
        self.queries: List[str] = []

    def hybrid_retrieve(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        self.queries.append(query)
        chunk = _chunk()
        return {"results": [chunk], "all_candidates": [chunk], "confidence": self.confidence, "fallback_used": False}

    def expand_to_parent_context(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return []


def _prepare(confidence: float, history: List[Dict[str, str]] | None = None) -> Any:
    return prepare_answer(
        StubRetrieval(confidence),  # type: ignore[arg-type]
        QueryDecomposer(), SimpleContextCompressor(), LLMClient(FakeGenaiClient(), "fake-model"),
        query=QUESTION, user_id="1", doc_version=0, top_k=5, mode="quick",
        recent_messages=history or [],
    )


@pytest.mark.parametrize(("confidence", "grounding"), [(85.0, "strict"), (45.0, "loose"), (10.0, "none")])
def test_grounding_follows_the_assembled_confidence(confidence: float, grounding: str) -> None:
    prepared = _prepare(confidence)

    assert prepared.grounding_level == grounding
    assert prepared.context.confidence == confidence


def test_prompt_is_what_build_prompt_makes_from_the_compressed_context() -> None:
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    prepared = _prepare(85.0, history)

    expected = LLMClient(FakeGenaiClient(), "fake-model").build_prompt(
        question=QUESTION, context_chunks=prepared.context.chunks, recent_messages=history,
        grounding_level="strict", mode="quick",
    )
    assert prepared.prompt == expected
    # Retrieved text stays in the final user turn, never the system instruction (G5).
    assert CHUNK_TEXT in prepared.prompt["current_user_text"]
    assert "Local file: DL_Unit5_RNN.pdf, Page 78" in prepared.prompt["current_user_text"]
    assert CHUNK_TEXT not in prepared.prompt["system_instruction"]
    assert len(prepared.prompt["contents"]) == 2
