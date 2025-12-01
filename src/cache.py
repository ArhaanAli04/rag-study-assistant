import os
import json
import hashlib
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL)

def _make_query_key(user_id: str | None, query: str) -> str:
    base = f"{user_id or 'anon'}::{query}"
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return f"query_cache:{h}"

def get_cached_response(user_id: str | None, query: str):
    key = _make_query_key(user_id, query)
    data = redis_client.get(key)
    if not data:
        return None
    return json.loads(data)

def set_cached_response(user_id: str | None, query: str, result, ttl_seconds: int = 3600):
    key = _make_query_key(user_id, query)
    redis_client.setex(key, ttl_seconds, json.dumps(result))
