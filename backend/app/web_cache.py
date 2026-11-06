import json
import redis
from typing import Any, Dict, List, Optional

from app.core.config import settings

WEB_CACHE_TTL_SECONDS = 3600  # 1 hour


def _get_client():
    return redis.from_url(settings.redis_url)


def get_cached_web_results(query: str) -> Optional[List[Dict[str, Any]]]:
    r = _get_client()
    key = f"websearch:{query}"
    val = r.get(key)
    if not val:
        return None
    try:
        return json.loads(val)
    except Exception:
        return None


def set_cached_web_results(query: str, results: List[Dict[str, Any]]):
    r = _get_client()
    key = f"websearch:{query}"
    r.setex(key, WEB_CACHE_TTL_SECONDS, json.dumps(results))
