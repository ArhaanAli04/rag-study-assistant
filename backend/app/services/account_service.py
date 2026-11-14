"""Delete everything the app holds about one user (B1)."""
import logging
from dataclasses import dataclass
from typing import Optional, Protocol

import redis
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from app.core.security import verify_password
from app.db.models.concept_map import ConceptMap, ConceptMapNode
from app.db.models import Chunk, Document, FailedQuery, Message, User, Session as ChatSession
from app.ingestion.upload_storage import FileStorage, StorageError, UnsafeUploadPath, is_user_key, user_prefix

logger = logging.getLogger("rag_assistant.account")


def authenticate_user(db: DbSession, email: str, password: str) -> Optional[User]:
    """The email/password user, or None. OAuth-only users have no password and can't log in this way."""
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


class UserScopedCache(Protocol):
    def clear_user(self, user_id: int) -> None: ...


class RetrievalL1Cache(Protocol):
    def l1_cache_purge_user(self, user_id: str) -> int: ...


@dataclass(frozen=True)
class AccountDeletionSummary:
    documents: int
    sessions: int
    messages: int
    concept_maps: int
    failed_queries: int
    files_removed: int
    # document_chunks rows (Day 15). The name predates them: FAISS / BM25 entries until then.
    index_entries_removed: int


def delete_user_account(
    db: DbSession,
    user: User,
    *,
    semantic_cache: UserScopedCache,
    retrieval_cache: RetrievalL1Cache,
    storage: FileStorage,
) -> AccountDeletionSummary:
    """Delete the user's rows (search chunks included) in one transaction, then files and caches.

    The database goes first because it is the source of truth: once the commit succeeds the
    account is unreachable through the API, and a failure in a later step leaves only an
    orphaned file or cache entry (logged), never an account whose files are already gone.
    """
    user_id = user.id
    legacy_keys = _legacy_keys_to_remove(db, user_id)

    try:
        session_ids = db.query(ChatSession.id).filter(ChatSession.user_id == user_id)
        map_ids = db.query(ConceptMap.id).filter(ConceptMap.user_id == user_id)
        # Children first and counted for the summary. ON DELETE CASCADE on every user_id (Day 15)
        # is the safety net for a child this list forgets, not the mechanism.
        chunks = db.query(Chunk).filter(Chunk.user_id == user_id).delete(synchronize_session=False)
        db.query(ConceptMapNode).filter(ConceptMapNode.map_id.in_(map_ids)).delete(
            synchronize_session=False
        )
        concept_maps = db.query(ConceptMap).filter(ConceptMap.user_id == user_id).delete(
            synchronize_session=False
        )
        messages = db.query(Message).filter(
            (Message.user_id == user_id) | Message.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        failed_queries = db.query(FailedQuery).filter(FailedQuery.user_id == user_id).delete(
            synchronize_session=False
        )
        sessions = db.query(ChatSession).filter(ChatSession.user_id == user_id).delete(
            synchronize_session=False
        )
        documents = db.query(Document).filter(Document.user_id == user_id).delete(
            synchronize_session=False
        )
        db.delete(user)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    files_removed = _remove_files(storage, user_id, legacy_keys)
    retrieval_cache.l1_cache_purge_user(str(user_id))
    try:
        semantic_cache.clear_user(user_id)
    except redis.RedisError:
        logger.warning("Could not clear the semantic cache of deleted user %s", user_id, exc_info=True)

    summary = AccountDeletionSummary(
        documents=documents,
        sessions=sessions,
        messages=messages,
        concept_maps=concept_maps,
        failed_queries=failed_queries,
        files_removed=files_removed,
        index_entries_removed=chunks,
    )
    logger.info("Deleted account %s: %s", user_id, summary)
    return summary


def _legacy_keys_to_remove(db: DbSession, user_id: int) -> list[str]:
    """Pre-G7 flat keys (uploads/<name>) of this user that no other user's row still references.

    Before G7 two users uploading the same filename shared one file, so deleting one account
    must not delete the other's document. Called before the rows are deleted.
    """
    own_keys = {key for (key,) in db.query(Document.file_path).filter(Document.user_id == user_id)}
    shared_keys = {
        key
        for (key,) in db.query(Document.file_path).filter(
            Document.file_path.in_(own_keys), Document.user_id != user_id
        )
    }
    return sorted(key for key in own_keys - shared_keys if not is_user_key(user_id, key))


def _remove_files(storage: FileStorage, user_id: int, legacy_keys: list[str]) -> int:
    """The user's whole uploads/<id>/ prefix, then their unshared legacy keys. Failures are logged:
    the account is already gone, and an orphaned file must not turn that into an error."""
    removed = 0
    try:
        removed += storage.delete_prefix(user_prefix(user_id))
    except (StorageError, UnsafeUploadPath):
        logger.warning("Could not delete the stored files of deleted user %s", user_id, exc_info=True)
    for key in legacy_keys:
        try:
            removed += 1 if storage.delete(key) else 0
        except (StorageError, UnsafeUploadPath):
            logger.warning("Could not delete legacy file %s of deleted user %s", key, user_id, exc_info=True)
    return removed
