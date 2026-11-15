"""CO6 (Day 16): what a chat turn writes, now that its writes are grouped into two commits.

The first commit holds the session and the user's message; the last one the topic tag, the
low-confidence failed query and the assistant's message. A stream error mid-answer must still keep
the user's message and the failed query, and store no assistant message.
"""
from typing import Any, Dict, Iterator, List

import pytest

from tests.conftest import Account
from tests.test_api_smoke import assert_contract, chat, parse_sse, upload

# No document uploaded and web search off: retrieval finds nothing, so confidence is below 30.
UNANSWERABLE = "What is the airspeed velocity of an unladen swallow?"


def _sessions(client: Any, account: Account) -> List[Dict[str, Any]]:
    return client.get("/sessions", headers=account.headers).json()


def _messages(client: Any, account: Account, session_id: int) -> List[Dict[str, Any]]:
    return client.get(f"/sessions/{session_id}/messages", headers=account.headers).json()


def _failed_queries(client: Any, account: Account) -> List[Dict[str, Any]]:
    return client.get("/analytics/failed-queries", headers=account.headers).json()


def test_the_first_turn_tags_the_sessions_topic(client: Any, account: Account) -> None:
    upload(client, account)

    session_id = assert_contract(chat(client, account))["metadata"]["session_id"]

    (session,) = [s for s in _sessions(client, account) if s["id"] == session_id]
    assert session["topic"] == "Computer Science"  # the fake classifier's reply


def test_a_low_confidence_turn_logs_a_failed_query_with_the_answer(client: Any, account: Account) -> None:
    result = assert_contract(chat(client, account, UNANSWERABLE))

    session_id = result["metadata"]["session_id"]
    assert result["metadata"]["confidence"] < 30
    assert [(m["role"], m["id"] == result["message_id"]) for m in _messages(client, account, session_id)] == [
        ("user", False), ("assistant", True)
    ]
    (logged,) = _failed_queries(client, account)
    assert (logged["query"], logged["reason"], logged["session_id"]) == (UNANSWERABLE, "low_confidence", session_id)


@pytest.fixture
def failing_stream(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    llm_client = client.app.state.services.chat_pipeline.llm_client

    def stream_then_fail(prompt: Any) -> Iterator[str]:
        yield "A first token, then "
        raise RuntimeError("Gemini dropped the stream")

    monkeypatch.setattr(llm_client, "stream_answer", stream_then_fail)


def test_a_stream_error_keeps_the_question_and_the_failed_query_but_no_answer(
    client: Any, account: Account, failing_stream: None
) -> None:
    response = client.get(
        "/chat/stream", params={"query": UNANSWERABLE, "session_id": 0, "mode": "quick", "token": account.token}
    )
    events = parse_sse(response.text)

    assert [e["type"] for e in events if isinstance(e, dict)] == ["metadata", "token", "error"]
    session_id = events[0]["data"]["session_id"]
    assert [m["role"] for m in _messages(client, account, session_id)] == ["user"]
    assert [fq["query"] for fq in _failed_queries(client, account)] == [UNANSWERABLE]
