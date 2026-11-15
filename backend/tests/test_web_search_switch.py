"""WEB_SEARCH_ENABLED (Day 17): false means no web client call anywhere in retrieval.

Added after a local "web off" run made 21 live Tavily searches: on Windows, `$env:TAVILY_API_KEY = ""`
deletes the variable, so the key in .env was used. The switch is a real boolean instead. Checked
through the real app with Tavily configured (the `web_search` fixture), for both paths that reach the
web: a chat turn (hybrid_retrieve) and a web-only concept map (get_web_chunks directly).
"""
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from tests.conftest import register_and_login
from tests.test_api_smoke import assert_contract, chat

WIKI = {
    "url": "https://en.wikipedia.org/wiki/Photosynthesis",
    "title": "Photosynthesis",
    "content": "Photosynthesis converts light energy into chemical energy in plants. " * 6,
}


@pytest.fixture
def app_with_web(monkeypatch: pytest.MonkeyPatch, web_search: Any, request: pytest.FixtureRequest) -> Iterator[Any]:
    # Settings are read when the services are built (the lifespan), so set the switch first.
    monkeypatch.setattr(settings, "WEB_SEARCH_ENABLED", request.param)
    web_search.results = [WIKI]
    with TestClient(create_app()) as client:
        yield client


@pytest.mark.parametrize("app_with_web", [False], indirect=True)
def test_web_search_disabled_makes_no_web_call_from_chat_or_concept_maps(app_with_web: Any, web_search: Any) -> None:
    client = app_with_web
    account = register_and_login(client)
    assert client.app.state.services.retrieval_service.web_search_enabled is False

    result = assert_contract(chat(client, account, query="How does photosynthesis work in plants?"))
    web_only_map = client.post(
        "/api/concepts/generate", headers=account.headers,
        json={"topic": "Photosynthesis", "use_documents": False, "use_web": True},
    )

    assert web_search.queries == []
    assert all(s.get("source_type") != "web" for s in result["metadata"]["sources"])
    assert web_only_map.status_code == 422  # nothing to build from: the web is off
    assert "Web search found nothing" in web_only_map.json()["detail"]


@pytest.mark.parametrize("app_with_web", [True], indirect=True)
def test_web_search_enabled_is_the_default_and_does_search(app_with_web: Any, web_search: Any) -> None:
    # Control: the same chat with the switch on reaches the (fake) Tavily client, so the test above
    # proves the switch, not a broken fixture.
    client = app_with_web
    account = register_and_login(client)

    assert_contract(chat(client, account, query="How does photosynthesis work in plants?"))

    assert web_search.queries != []


def test_the_setting_defaults_to_true() -> None:
    assert type(settings).model_fields["WEB_SEARCH_ENABLED"].default is True
