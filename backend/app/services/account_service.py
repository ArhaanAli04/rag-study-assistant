"""Delete everything the app holds about one user (B1)."""
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, Sequence

import redis
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from app.core.security import verify_password
from app.db.models.concept_map import ConceptMap, ConceptMapNode
from app.db.models import Document, FailedQuery, Message, User, Session as ChatSession
from app.ingestion.upload_storage import UnsafeUploadPath, ensure_inside_root, user_upload_dir

logger = logging.getLogger("rag_assistant.account")


def authenticate_user(db: DbSession, email: str, password: str) -> Optional[User]:
    """The email/password user, or None. OAuth-only users have no password and can't log in this way."""
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


class UserScopedIndex(Protocol):
    def mark_deleted_by_user(self, user_id: str) -> int: ...


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
    index_entries_removed: int


def delete_user_account(
    db: DbSession,
    user: User,
    *,
    indexes: Sequence[UserScopedIndex],
    semantic_cache: UserScopedCache,
    retrieval_cache: RetrievalL1Cache,
    upload_root: Path,
) -> AccountDeletionSummary:
    """Delete the user's rows in one transaction, then their files, index entries and caches.

    The database goes first because it is the source of truth: once the commit succeeds the
    account is unreachable through the API, and a failure in a later step leaves only an
    orphaned file or cache entry (logged), never an account whose files are already gone.
    """
    user_id = user.id
    legacy_files = _legacy_files_to_remove(db, user_id, upload_root)

    try:
        session_ids = db.query(ChatSession.id).filter(ChatSession.user_id == user_id)
        map_ids = db.query(ConceptMap.id).filter(ConceptMap.user_id == user_id)
        # Bulk deletes skip ORM cascades and SQLite runs without foreign keys, so children go first.
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

    files_removed = _remove_legacy_files(legacy_files) + _remove_user_dir(upload_root, user_id)
    index_entries_removed = sum(index.mark_deleted_by_user(str(user_id)) for index in indexes)
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
        index_entries_removed=index_entries_removed,
    )
    logger.info("Deleted account %s: %s", user_id, summary)
    return summary


def _legacy_files_to_remove(db: DbSession, user_id: int, upload_root: Path) -> list[Path]:
    """Pre-G7 flat-path files of this user that no other user's row still references.

    Before G7 two users uploading the same filename shared one file on disk, so deleting
    one account must not delete the other's document.
    """
    own_paths = {
        path for (path,) in db.query(Document.file_path).filter(Document.user_id == user_id)
    }
    shared_paths = {
        path
        for (path,) in db.query(Document.file_path).filter(
            Document.file_path.in_(own_paths), Document.user_id != user_id
        )
    }
    own_dir = user_upload_dir(upload_root, user_id).resolve()
    legacy: list[Path] = []
    for path in sorted(own_paths - shared_paths):
        try:
            resolved = ensure_inside_root(upload_root, Path(path))
        except UnsafeUploadPath:
            logger.warning("Not deleting %s of user %s: outside the upload root", path, user_id)
            continue
        if not resolved.is_relative_to(own_dir):
            legacy.append(resolved)
    return legacy


def _remove_legacy_files(paths: list[Path]) -> int:
    removed = 0
    for path in paths:
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Could not delete uploaded file %s", path, exc_info=True)
    return removed


def _remove_user_dir(upload_root: Path, user_id: int) -> int:
    user_dir = user_upload_dir(upload_root, user_id)
    if not user_dir.is_dir():
        return 0
    file_count = sum(len(files) for _, _, files in os.walk(user_dir))
    try:
        shutil.rmtree(user_dir)
    except OSError:
        logger.warning("Could not delete upload directory %s", user_dir, exc_info=True)
        return 0
    return file_count
