"""R5 (Day 17): concept maps built from the user's documents, through the real app.

A document indexed through POST /upload is what the concept-map retriever returns; its nodes cite
that file and a page; a documents-only map never searches the web; and a deleted document stops
appearing in maps (doc_version reaches the retrieval cache key).
"""
import json
from typing import Any, Dict

from tests.conftest import Account
from tests.fakes import FakeGemini
from tests.test_api_smoke import upload

# Words from samples.pdf, so full-text search finds its chunks whatever the fake embeddings rank first.
TOPIC = "retrieval augmented generation pipeline for uploaded documents"


def concept_reply(*source_ids: str) -> str:
    return json.dumps({
        "topic": TOPIC,
        "off_topic": False,
        "nodes": [
            {"id": "rag", "label": "RAG pipeline", "definition": "Retrieve, then generate.", "source_ids": list(source_ids)},
            {"id": "chunking", "label": "Chunking", "definition": "Splitting documents.", "source_ids": ["D99"]},
        ],
        "edges": [{"from": "rag", "to": "chunking", "label": "starts with"}],
    })


def generate(client: Any, account: Account, **body: Any) -> Any:
    payload: Dict[str, Any] = {"topic": TOPIC, "use_documents": True, "use_web": False, **body}
    return client.post("/api/concepts/generate", headers=account.headers, json=payload)


def test_a_documents_only_map_cites_the_uploaded_file_and_page_and_never_searches_the_web(
    client: Any, account: Account, gemini: FakeGemini, web_search: Any
) -> None:
    assert upload(client, account).status_code == 200
    gemini.replies.append(concept_reply("D1", "[D2]"))

    generated = generate(client, account)

    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["sources"]["documents"] > 0
    assert body["sources"]["web"] == 0
    assert body["sources"]["document_sources"] == ["samples.pdf"]
    assert web_search.queries == []  # web search is on for this test, yet not called
    prompt = gemini.prompts[-1]
    assert "[D1] samples.pdf — p. " in prompt

    nodes = {n["id"]: n for n in body["nodes"]}
    assert nodes["rag"]["source_type"] == "document"
    assert nodes["rag"]["sources"]
    assert all(s.startswith("samples.pdf — p. ") for s in nodes["rag"]["sources"])
    assert (nodes["chunking"]["source_type"], nodes["chunking"]["sources"]) == ("unknown", [])

    detail = client.get(f"/api/concepts/maps/{body['map_id']}", headers=account.headers).json()
    assert {n["id"]: n["sources"] for n in detail["nodes"]}["rag"] == nodes["rag"]["sources"]


def test_a_topic_the_documents_dont_cover_is_refused_and_not_saved(
    client: Any, account: Account, gemini: FakeGemini
) -> None:
    # Day 17 live check: vector search returned the nearest (photosynthesis) chunks for "French
    # Revolution" and a map was built from them. The model now flags it and nothing is saved.
    assert upload(client, account).status_code == 200
    gemini.replies.append(json.dumps({"topic": "French Revolution", "off_topic": True, "nodes": [], "edges": []}))

    generated = generate(client, account, topic="French Revolution")

    assert generated.status_code == 422, generated.text
    assert generated.json()["detail"] == (
        "Your documents don't seem to cover 'French Revolution'. Try another topic or turn on web search."
    )
    assert "off_topic" in gemini.prompts[-1]  # the model was asked to judge the passages
    assert client.get("/api/concepts/maps", headers=account.headers).json()["maps"] == []


def test_a_deleted_document_stops_appearing_in_maps(client: Any, account: Account, gemini: FakeGemini) -> None:
    uploaded = upload(client, account).json()
    gemini.replies.append(concept_reply("D1"))
    assert generate(client, account).status_code == 200

    assert client.delete(f"/documents/{uploaded['document_id']}", headers=account.headers).status_code == 200
    again = generate(client, account)

    # With a constant doc_version the retrieval cache replayed the deleted file's chunks here.
    assert again.status_code == 422, again.text
    assert "No passages in your documents" in again.json()["detail"]


def test_documents_only_without_documents_is_refused_and_skips_the_llm(
    client: Any, account: Account, gemini: FakeGemini
) -> None:
    generated = generate(client, account)

    assert generated.status_code == 422
    assert gemini.prompts == []
    assert client.get("/api/concepts/maps", headers=account.headers).json()["maps"] == []


def test_no_source_selected_is_refused(client: Any, account: Account) -> None:
    generated = generate(client, account, use_documents=False, use_web=False)

    assert generated.status_code == 422
    assert "at least one source" in generated.json()["detail"]
