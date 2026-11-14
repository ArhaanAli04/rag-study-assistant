"""The composition root: every long-lived object the app uses, built once and wired together here.

The app's lifespan calls build_services() at startup and puts the result on app.state; routes reach
it through app.api.deps.get_services. Nothing else in app/ constructs these, so each exists once per
process: one Gemini client (~3 s to build on the dev host), one embedding service, one chunk search.
Since Day 15 the search indexes live in Postgres (document_chunks), not in this process.
"""
from dataclasses import dataclass

import redis
from google import genai

from app.core.config import settings
from app.core.gemini import build_gemini_client
from app.db.session import SessionLocal
from app.generation.concept_extractor import ConceptExtractor
from app.generation.llm_client import LLMClient
from app.generation.topic_classifier import TopicClassifier
from app.retrieval.concept_map_retriever import ConceptMapRetriever
from app.retrieval.context_compressor import SimpleContextCompressor
from app.retrieval.embeddings import EmbeddingService
from app.retrieval.pg_chunk_search import PgChunkSearch
from app.retrieval.query_decomposer import QueryDecomposer
from app.retrieval.retrieval_service import RetrievalService
from app.services.caches.query_cache import QueryCache
from app.services.caches.semantic_cache import SemanticCache
from app.services.caches.web_cache import WebCache
from app.services.chat_pipeline import ChatPipeline
from app.services.concept_map_service import ConceptMapService
from app.services.indexing_service import IndexingService


@dataclass
class Services:
    gemini_client: genai.Client
    redis_client: redis.Redis
    semantic_cache_redis_client: redis.Redis
    embedding_service: EmbeddingService
    indexing_service: IndexingService
    retrieval_service: RetrievalService
    llm_client: LLMClient
    semantic_cache: SemanticCache
    chat_pipeline: ChatPipeline
    concept_map_service: ConceptMapService

    def close(self) -> None:
        self.redis_client.close()
        self.semantic_cache_redis_client.close()


def build_services() -> Services:
    gemini_client = build_gemini_client()
    redis_client = redis.from_url(settings.redis_url)
    semantic_cache_redis_client = redis.from_url(settings.semantic_cache_redis_url)

    embedding_service = EmbeddingService(gemini_client)
    retrieval_service = RetrievalService(
        embedding_service=embedding_service,
        chunk_search=PgChunkSearch(SessionLocal),
        query_cache=QueryCache(redis_client),
        web_cache=WebCache(redis_client),
    )
    generation_model = settings.GEMINI_GENERATION_MODEL
    llm_client = LLMClient(gemini_client, generation_model)
    semantic_cache = SemanticCache(embedding_service=embedding_service, redis_client=semantic_cache_redis_client)

    return Services(
        gemini_client=gemini_client,
        redis_client=redis_client,
        semantic_cache_redis_client=semantic_cache_redis_client,
        embedding_service=embedding_service,
        indexing_service=IndexingService(embedding_service),
        retrieval_service=retrieval_service,
        llm_client=llm_client,
        semantic_cache=semantic_cache,
        chat_pipeline=ChatPipeline(
            retrieval_service=retrieval_service,
            llm_client=llm_client,
            topic_classifier=TopicClassifier(gemini_client, generation_model),
            semantic_cache=semantic_cache,
            query_decomposer=QueryDecomposer(),
            compressor=SimpleContextCompressor(),
        ),
        concept_map_service=ConceptMapService(
            ConceptMapRetriever(retrieval_service), ConceptExtractor(gemini_client, generation_model)
        ),
    )
