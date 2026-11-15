"""Day 9: building the app costs nothing; starting it builds one Gemini client, shared by every service."""
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.retrieval.embeddings import EMBED_TEXTS_PER_MINUTE, INDEXING_MAX_ATTEMPTS, QUERY_MAX_ATTEMPTS
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
        assert services.embedding_service.client is shared
        assert services.query_embedding_service.client is shared
        # Day 16: uploads retry, the chat path (retrieval, semantic cache) gets one attempt.
        assert services.indexing_service.embedding_service is services.embedding_service
        assert services.embedding_service.max_attempts == INDEXING_MAX_ATTEMPTS
        assert services.retrieval_service.embedding_service is services.query_embedding_service
        assert services.semantic_cache.embedding_service is services.query_embedding_service
        assert services.query_embedding_service.max_attempts == QUERY_MAX_ATTEMPTS
        # Only uploads pace themselves under the free tier's per-text limit; chat calls embed one text.
        assert services.embedding_service.texts_per_minute == EMBED_TEXTS_PER_MINUTE
        assert services.query_embedding_service.texts_per_minute is None
        assert services.chat_pipeline.topic_classifier.client is shared
        assert services.concept_map_service.extractor.client is shared
        # B9: the three generation roles all use the one Settings model.
        model = settings.GEMINI_GENERATION_MODEL
        assert services.llm_client.model_name == model
        assert services.chat_pipeline.topic_classifier.model_name == model
        assert services.concept_map_service.extractor.model_name == model
        # The concept-map retriever searches the index /upload writes to, not a private one (R5).
        assert services.concept_map_service.retriever.retrieval_service is services.retrieval_service


def test_startup_makes_no_embedding_call() -> None:
    # The vector size comes from EMBEDDING_DIM, not from embedding "hello world" at boot.
    FakeGenaiClient.gemini.reset()

    with TestClient(create_app()):
        assert FakeGenaiClient.gemini.embed_calls == 0
