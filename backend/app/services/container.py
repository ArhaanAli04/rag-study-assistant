"""The composition root: every long-lived object the app uses, built once and wired together here.

The app's lifespan calls build_services() at startup and puts the result on app.state; routes reach
it through app.api.deps.get_services. Nothing else in app/ constructs these, so each exists once per
process: one Gemini client (~3 s to build on the dev host), one FAISS index, one BM25 index.
"""
from dataclasses import dataclass

import redis
from google import genai

from app.core.config import settings
from app.core.gemini import build_gemini_client
from app.generation.concept_extractor import ConceptExtractor
from app.generation.llm_client import LLMClient
from app.generation.topic_classifier import TopicClassifier
from app.ingestion.indexing_pipeline import IndexingPipeline
from app.retrieval.concept_map_retriever import ConceptMapRetriever
from app.retrieval.context_compressor import SimpleContextCompressor
from app.retrieval.embeddings import EmbeddingService
from app.retrieval.index_builder import IndexBuilder
from app.retrieval.keyword_index import BM25KeywordIndex
from app.retrieval.query_decomposer import QueryDecomposer
from app.retrieval.retrieval_service import RetrievalService
from app.services.caches.query_cache import QueryCache
from app.services.caches.semantic_cache import SemanticCache
from app.services.caches.web_cache import WebCache
from app.services.chat_pipeline import ChatPipeline
from app.services.concept_map_service import ConceptMapService


@dataclass
class Services:
    gemini_client: genai.Client
    redis_client: redis.Redis
    semantic_cache_redis_client: redis.Redis
    index_builder: IndexBuilder
    bm25_index: BM25KeywordIndex
    indexing_pipeline: IndexingPipeline
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

    index_builder = IndexBuilder(EmbeddingService(gemini_client))
    bm25_index = BM25KeywordIndex()
    retrieval_service = RetrievalService(
        index_builder=index_builder,
        bm25_index=bm25_index,
        query_cache=QueryCache(redis_client),
        web_cache=WebCache(redis_client),
    )
    generation_model = settings.GEMINI_GENERATION_MODEL
    llm_client = LLMClient(gemini_client, generation_model)
    semantic_cache = SemanticCache(index_builder=index_builder, redis_client=semantic_cache_redis_client)

    return Services(
        gemini_client=gemini_client,
        redis_client=redis_client,
        semantic_cache_redis_client=semantic_cache_redis_client,
        index_builder=index_builder,
        bm25_index=bm25_index,
        indexing_pipeline=IndexingPipeline(index_builder=index_builder, bm25_index=bm25_index),
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
