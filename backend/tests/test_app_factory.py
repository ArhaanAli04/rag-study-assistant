"""Day 9: building the app costs nothing; starting it builds one Gemini client, shared by every service."""
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import FakeGenaiClient


def test_create_app_builds_no_gemini_client() -> None:
    # create_app() is what `import app.main` runs; it used to build five clients (~3 s each).
    before = FakeGenaiClient.instances

    create_app()

    assert FakeGenaiClient.instances == before


def test_startup_builds_exactly_one_shared_gemini_client() -> None:
    app = create_app()
    before = FakeGenaiClient.instances

    with TestClient(app):
        services = app.state.services
        assert FakeGenaiClient.instances == before + 1
        shared = services.gemini_client
        assert services.llm_client.client is shared
        assert services.index_builder.embedding_service.client is shared
        assert services.chat_pipeline.topic_classifier.client is shared
        assert services.concept_map_service.extractor.client is shared
        # The concept-map retriever searches the index /upload writes to, not a private one (R5).
        assert services.concept_map_service.retriever.retrieval_service is services.retrieval_service


def test_startup_makes_no_embedding_call() -> None:
    # The FAISS dimension comes from EMBEDDING_DIM, not from embedding "hello world" at boot.
    FakeGenaiClient.gemini.reset()

    with TestClient(create_app()):
        assert FakeGenaiClient.gemini.embed_calls == 0
