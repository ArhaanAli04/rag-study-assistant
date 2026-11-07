import hashlib
import json
from typing import Any, Optional

import redis

QUERY_CACHE_TTL_SECONDS = 3600


def _make_query_key(user_id: str | None, query: str, doc_version: int) -> str:
    base = f"{user_id or 'anon'}::{doc_version}::{query}"
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return f"query_cache:{h}"


class QueryCache:
    """/search results in Redis, keyed by user + doc_version + query (doc_version bump = invalidation)."""

    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client

    def get(self, user_id: str | None, query: str, doc_version: int) -> Optional[Any]:
        data = self.redis.get(_make_query_key(user_id, query, doc_version))
        if not data:
            return None
        return json.loads(data)

    def set(
        self,
        user_id: str | None,
        query: str,
        doc_version: int,
        result: Any,
        ttl_seconds: int = QUERY_CACHE_TTL_SECONDS,
    ) -> None:
        self.redis.setex(_make_query_key(user_id, query, doc_version), ttl_seconds, json.dumps(result))
