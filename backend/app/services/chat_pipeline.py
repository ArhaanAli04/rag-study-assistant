"""The chat pipeline behind GET /chat/stream — the only chat endpoint since Day 9 (POST /chat, a
drifted copy of these steps, was deleted).

guards → semantic cache → session + history + topic tag → decompose → hybrid retrieve per
sub-query → parent expansion → compress → grounding → prompt → stream → store.

The SSE frames are a contract with frontend/src/components/ChatWindow.js:
    metadata → token… → message_id → [DONE]       (answer, fresh or replayed from the cache)
    metadata(refused) → token → [DONE]            (guard refusal; not stored, so no message_id)
    metadata → token… → error                     (LLM failure mid-stream)
"""
import datetime
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Iterator, List, Union

from sqlalchemy.orm import Session

from app.db.database import FailedQuery, Message, Session as ChatSession, User
from app.core.errors import UserFriendlyError
from app.generation.llm_client import LLMClient
from app.generation.topic_classifier import TopicClassifier
from app.retrieval.confidence import LOW_CONFIDENCE_BELOW, grounding_level as grounding_for
from app.retrieval.context_assembly import assemble_context
from app.retrieval.context_compressor import SimpleContextCompressor
from app.retrieval.query_decomposer import QueryDecomposer
from app.retrieval.retrieval_service import RetrievalService
from app.services.caches.semantic_cache import SemanticCache
from app.services.chat_guards import (
    INJECTION_REFUSAL,
    UNSAFE_REFUSAL,
    find_injection_phrase,
    find_unsafe_keyword,
    refusal_sse_events,
)
from app.services.session_service import add_message, get_or_create_session, get_recent_messages

logger = logging.getLogger("rag_assistant.chat")

TOPIC_MIN_CONFIDENCE = 0.3

NO_CACHE = {"Cache-Control": "no-cache"}


@dataclass
class ChatStream:
    """What the route wraps in a StreamingResponse."""

    events: Union[Iterator[str], AsyncIterator[str]]
    headers: Dict[str, str]


def _sse(payload: object) -> str:
    return f"data: {json.dumps(payload)}\n\n"


class ChatPipeline:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        llm_client: LLMClient,
        topic_classifier: TopicClassifier,
        semantic_cache: SemanticCache,
        query_decomposer: QueryDecomposer,
        compressor: SimpleContextCompressor,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.llm_client = llm_client
        self.topic_classifier = topic_classifier
        self.semantic_cache = semantic_cache
        self.query_decomposer = query_decomposer
        self.compressor = compressor

    def answer(
        self, db: Session, user: User, query: str, session_id: int, top_k: int, mode: str
    ) -> ChatStream:
        """Run everything up to generation now, so a retrieval failure is a normal HTTP error;
        generation then happens while the returned events are streamed."""
        user_id_int = user.id
        doc_version = getattr(user, "doc_version", 0)

        # Refusals go out as a 200 event stream: EventSource can't read the body of a 400 or a
        # text/plain reply and would show a connection error instead. Refused turns are not
        # stored: a stored one would be replayed to Gemini as history.
        injection_phrase = find_injection_phrase(query)
        if injection_phrase is not None:
            logger.warning(f"Prompt-injection phrase {injection_phrase!r} refused for user {user_id_int}")
            return ChatStream(refusal_sse_events(INJECTION_REFUSAL, session_id, mode), NO_CACHE)

        if find_unsafe_keyword(query) is not None:
            return ChatStream(refusal_sse_events(UNSAFE_REFUSAL, session_id, mode), NO_CACHE)

        cached = self.semantic_cache.lookup(query, user_id=user_id_int, user_doc_version=doc_version, mode=mode)
        if cached:
            return self._replay_cached(db, user_id_int, query, session_id, mode, cached)

        chat_session = get_or_create_session(db, user_id_int, session_id, query)
        message_count = db.query(Message).filter(Message.session_id == chat_session.id).count()

        # History is read BEFORE the current message is added, so the question isn't sent twice.
        recent_messages = [
            {"role": m.role, "content": m.content}
            for m in get_recent_messages(db, chat_session.id)
        ]
        add_message(db, chat_session.id, user_id_int, role="user", content=query)
        self._tag_topic(db, chat_session, query, message_count)

        compressed_context, final_confidence, any_fallback = self._retrieve(
            query, str(user_id_int), doc_version, top_k
        )
        grounding_level = grounding_for(final_confidence)

        prompt = self.llm_client.build_prompt(
            question=query,
            context_chunks=compressed_context,
            recent_messages=recent_messages,
            grounding_level=grounding_level,
            mode=mode,
        )
        events = self._generate(
            db, user_id_int, query, chat_session.id, doc_version, mode,
            prompt, compressed_context, final_confidence, any_fallback, grounding_level,
        )
        return ChatStream(events, {})

    def _tag_topic(self, db: Session, chat_session: ChatSession, query: str, message_count: int, cached: bool = False) -> None:
        if not (message_count == 0 or chat_session.topic == "General"):
            return
        label = "tagged (cached)" if cached else "tagged"
        try:
            topic_result = self.topic_classifier.classify_topic(query)
            if topic_result["confidence"] > TOPIC_MIN_CONFIDENCE:
                chat_session.topic = topic_result["topic"]
                db.commit()
                logger.info(
                    f" Session {chat_session.id} {label}: {topic_result['topic']} "
                    f"(confidence: {topic_result['confidence']:.2f})"
                )
        # A topic tag is cosmetic: whatever goes wrong, the answer must still be sent.
        except Exception as e:
            logger.error(f"Topic classification error{' (cached)' if cached else ''}: {e}")

    def _retrieve(
        self, query: str, user_id: str, doc_version: int, top_k: int
    ) -> tuple[List[Dict[str, Any]], float, bool]:
        context = assemble_context(
            self.retrieval_service, self.query_decomposer, self.compressor,
            query=query, user_id=user_id, doc_version=doc_version, top_k=top_k,
        )
        return context.chunks, context.confidence, context.fallback_used

    def _replay_cached(
        self, db: Session, user_id_int: int, query: str, session_id: int, mode: str, cached: Dict[str, Any]
    ) -> ChatStream:
        chat_session = get_or_create_session(db, user_id_int, session_id, query)
        message_count = db.query(Message).filter(Message.session_id == chat_session.id).count()
        add_message(db, chat_session.id, user_id_int, role="user", content=query)
        self._tag_topic(db, chat_session, query, message_count, cached=True)

        async def cached_stream() -> AsyncIterator[str]:
            metadata = {
                "session_id": chat_session.id,
                "confidence": cached.get("confidence", 100),
                "fallback_used": False,
                "grounding_level": cached.get("grounding_level", "strict"),
                "sources": cached.get("sources", []),
                "mode": mode,
            }
            yield _sse({"type": "metadata", "data": metadata})

            cached_answer = cached.get("answer", "")
            for char in cached_answer:
                yield _sse({"type": "token", "data": char})

            assistant_msg_id = add_message(
                db, chat_session.id, user_id_int,
                role="assistant",
                content=cached_answer,
                sources=",".join([str(s.get("file_name", s.get("url", ""))) for s in cached.get("sources", [])]),
            )
            yield _sse({"type": "message_id", "data": assistant_msg_id})
            yield "data: [DONE]\n\n"

        return ChatStream(cached_stream(), {**NO_CACHE, "Connection": "keep-alive"})

    async def _generate(
        self,
        db: Session,
        user_id_int: int,
        query: str,
        chat_session_id: int,
        doc_version: int,
        mode: str,
        prompt: Dict[str, Any],
        compressed_context: List[Dict[str, Any]],
        final_confidence: float,
        any_fallback: bool,
        grounding_level: str,
    ) -> AsyncIterator[str]:
        try:
            metadata = {
                "session_id": chat_session_id,
                "confidence": final_confidence,
                "fallback_used": any_fallback,
                "grounding_level": grounding_level,
                "sources": [c["metadata"] for c in compressed_context],
                "mode": mode,
            }
            yield _sse({"type": "metadata", "data": metadata})

            if final_confidence < LOW_CONFIDENCE_BELOW:
                db.add(FailedQuery(
                    user_id=str(user_id_int),
                    session_id=chat_session_id,
                    query=query,
                    confidence=final_confidence,
                    feedback=None,
                    reason="low_confidence",
                    comment=f"Automatic log: confidence={final_confidence}",
                    timestamp=datetime.datetime.utcnow(),
                ))
                db.commit()

            full_answer = ""
            for token in self.llm_client.stream_answer(prompt):
                full_answer += token
                yield _sse({"type": "token", "data": token})

            assistant_msg_id = add_message(
                db, chat_session_id, user_id_int,
                role="assistant",
                content=full_answer,
                sources=",".join([c["metadata"].get("file_name", c["metadata"].get("url", "")) for c in compressed_context]),
            )
            yield _sse({"type": "message_id", "data": assistant_msg_id})
            yield "data: [DONE]\n\n"

            resp_dict = {
                "answer": full_answer,
                "session_id": chat_session_id,
                "confidence": final_confidence,
                "fallback_used": any_fallback,
                "grounding_level": grounding_level,
                "sources": [c["metadata"] for c in compressed_context],
                "followups": [],
            }
            self.semantic_cache.store(query, resp_dict, user_id=user_id_int, user_doc_version=doc_version, mode=mode)

        except RuntimeError as e:
            error_type = UserFriendlyError.classify_error(e)
            error_response = UserFriendlyError.get_message(error_type)
            logger.error(f"Stream RuntimeError ({error_type}): {e}")
            yield _sse({"type": "error", "data": error_response["error"]})
        # Last resort once the 200 and headers are sent: the client can only be told in-stream.
        except Exception as e:
            logger.error(f"Unexpected stream error: {e}")
            error_response = UserFriendlyError.get_message("unknown")
            yield _sse({"type": "error", "data": error_response["error"]})
