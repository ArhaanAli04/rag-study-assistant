import json
from typing import Any, Dict, List, Optional

import redis

WEB_CACHE_TTL_SECONDS = 3600  # 1 hour


class WebCache:
    """Tavily chunks without embeddings (they are re-embedded on a hit), shared by all users."""

    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client

    def get(self, query: str) -> Optional[List[Dict[str, Any]]]:
        val = self.redis.get(f"websearch:{query}")
        if not val:
            return None
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return None  # a corrupt entry is a miss; the fresh result overwrites it

    def set(self, query: str, results: List[Dict[str, Any]]) -> None:
        self.redis.setex(f"websearch:{query}", WEB_CACHE_TTL_SECONDS, json.dumps(results))
