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
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Union

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import FailedQuery, User
from app.db.repositories import sessions as sessions_repo
from app.core.errors import UserFriendlyError
from app.generation.llm_client import LLMClient
from app.generation.topic_classifier import TopicClassifier
from app.retrieval.confidence import LOW_CONFIDENCE_BELOW
from app.retrieval.context_compressor import SimpleContextCompressor
from app.retrieval.query_decomposer import QueryDecomposer
from app.retrieval.retrieval_service import RetrievalService
from app.services.answer_preparation import prepare_answer
from app.services.caches.semantic_cache import SemanticCache
from app.services.chat_guards import (
    INJECTION_REFUSAL,
    UNSAFE_REFUSAL,
    find_injection_phrase,
    find_unsafe_keyword,
    refusal_sse_events,
)
from app.services.session_service import (
    DEFAULT_TOPIC,
    add_message,
    get_or_create_session,
    get_recent_messages,
)

logger = logging.getLogger("rag_assistant.chat")

TOPIC_MIN_CONFIDENCE = 0.3

NO_CACHE = {"Cache-Control": "no-cache"}


@dataclass(frozen=True)
class _Turn:
    """What the rest of a turn needs from its first transaction, as plain values."""

    session_id: int
    needs_topic: bool
    history: List[Dict[str, str]]


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

        turn = self._open_turn(db, user_id_int, session_id, query, load_history=True)
        topic = self._classify_topic(turn, query)

        prepared = prepare_answer(
            self.retrieval_service, self.query_decomposer, self.compressor, self.llm_client,
            query=query, user_id=str(user_id_int), doc_version=doc_version, top_k=top_k,
            mode=mode, recent_messages=turn.history,
        )
        events = self._generate(
            db, user_id_int, query, turn.session_id, doc_version, mode,
            prepared.prompt, prepared.context.chunks, prepared.context.confidence,
            prepared.context.fallback_used, prepared.grounding_level, topic,
        )
        return ChatStream(events, {})

    def _open_turn(self, db: Session, user_id: int, session_id: int, query: str, load_history: bool) -> "_Turn":
        """The turn's first transaction (CO6): session, history and the user's message, one commit.

        Everything later needs only plain values from here: after the commit the ORM objects are
        expired, and touching one would reload it with another round trip.
        """
        chat_session, created = get_or_create_session(db, user_id, session_id, query)
        turn = _Turn(
            session_id=chat_session.id,
            # Tag while the session still has the default topic (a new session always does).
            needs_topic=chat_session.topic in (None, DEFAULT_TOPIC),
            # Read BEFORE the current message is added, so the question isn't sent twice; a new
            # session has none, so it skips the query.
            history=[] if created or not load_history else [
                {"role": m.role, "content": m.content} for m in get_recent_messages(db, chat_session.id)
            ],
        )
        add_message(db, turn.session_id, user_id, role="user", content=query)
        db.commit()
        return turn

    def _classify_topic(self, turn: "_Turn", query: str, cached: bool = False) -> Optional[str]:
        """The session's topic tag, or None. An LLM call, made with no transaction open; the tag is
        written with the turn's last commit."""
        if not turn.needs_topic:
            return None
        label = "tagged (cached)" if cached else "tagged"
        try:
            topic_result = self.topic_classifier.classify_topic(query)
        # A topic tag is cosmetic: whatever goes wrong, the answer must still be sent.
        except Exception as e:
            logger.error(f"Topic classification error{' (cached)' if cached else ''}: {e}")
            return None
        if topic_result["confidence"] <= TOPIC_MIN_CONFIDENCE:
            return None
        logger.info(
            f" Session {turn.session_id} {label}: {topic_result['topic']} "
            f"(confidence: {topic_result['confidence']:.2f})"
        )
        return topic_result["topic"]

    def _replay_cached(
        self, db: Session, user_id_int: int, query: str, session_id: int, mode: str, cached: Dict[str, Any]
    ) -> ChatStream:
        turn = self._open_turn(db, user_id_int, session_id, query, load_history=False)
        topic = self._classify_topic(turn, query, cached=True)

        async def cached_stream() -> AsyncIterator[str]:
            metadata = {
                "session_id": turn.session_id,
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

            assistant_msg_id = self._close_turn(
                db, turn.session_id, user_id_int, topic, cached_answer,
                ",".join([str(s.get("file_name", s.get("url", ""))) for s in cached.get("sources", [])]),
            )
            yield _sse({"type": "message_id", "data": assistant_msg_id})
            yield "data: [DONE]\n\n"

        return ChatStream(cached_stream(), {**NO_CACHE, "Connection": "keep-alive"})

    @staticmethod
    def _close_turn(
        db: Session, session_id: int, user_id: int, topic: Optional[str], answer: str, sources: str
    ) -> int:
        """The turn's last transaction (CO6): the topic tag, any failed query added during the turn,
        and the assistant's message, one commit. Returns the message id (read back by the flush)."""
        if topic is not None:
            sessions_repo.set_topic(db, session_id, user_id, topic)
        message_id = add_message(db, session_id, user_id, role="assistant", content=answer, sources=sources)
        db.commit()
        return message_id

    @staticmethod
    def _commit_failed_query(db: Session) -> None:
        """After a stream error: keep the failed query the turn may have logged (no assistant message)."""
        if not db.new:
            return
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Could not store the failed query after a stream error")

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
        topic: Optional[str],
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
                # Only added here (no SQL yet): it is written with the assistant's message, so no
                # transaction stays open while the answer streams.
                db.add(FailedQuery(
                    user_id=user_id_int,
                    session_id=chat_session_id,
                    query=query,
                    confidence=final_confidence,
                    feedback=None,
                    reason="low_confidence",
                    comment=f"Automatic log: confidence={final_confidence}",
                    timestamp=datetime.datetime.utcnow(),
                ))

            full_answer = ""
            for token in self.llm_client.stream_answer(prompt):
                full_answer += token
                yield _sse({"type": "token", "data": token})

            assistant_msg_id = self._close_turn(
                db, chat_session_id, user_id_int, topic, full_answer,
                ",".join([c["metadata"].get("file_name", c["metadata"].get("url", "")) for c in compressed_context]),
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
            self._commit_failed_query(db)
            yield _sse({"type": "error", "data": error_response["error"]})
        # Last resort once the 200 and headers are sent: the client can only be told in-stream.
        except Exception as e:
            logger.error(f"Unexpected stream error: {e}")
            self._commit_failed_query(db)
            error_response = UserFriendlyError.get_message("unknown")
            yield _sse({"type": "error", "data": error_response["error"]})
