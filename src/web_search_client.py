import os
from typing import List, Dict, Any
from tavily import TavilyClient  # [web:56][web:59]
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()
ALLOWED_DOMAINS = [
    "wikipedia.org",
    ".edu",
    "arxiv.org",
    "stackexchange.com",
    "stackoverflow.com",
    "geeksforgeeks.org",
]


def _is_credible(url: str) -> bool:
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False
    for dom in ALLOWED_DOMAINS:
        if dom.startswith("."):
            if netloc.endswith(dom):
                return True
        elif dom in netloc:
            return True
    return False


class WebSearchClient:
    """
    Light wrapper around Tavily Search API for academic/technical sources.
    """

    def __init__(self, api_key: str | None = None):
        api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY not set")
        self.client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Returns a list of results: {url, title, content}
        """
        resp = self.client.search(
            query,
            max_results=max_results,
            search_depth="advanced",
            topic="general",
            include_answer=False,
        )  # [web:56][web:59][web:65]
        raw_results = resp.get("results", [])
        filtered: List[Dict[str, Any]] = []
        for r in raw_results:
            url = r.get("url") or ""
            if not _is_credible(url):
                continue
            filtered.append(
                {
                    "url": url,
                    "title": r.get("title", ""),
                    "content": r.get("content", "") or r.get("raw_content", ""),
                }
            )
        return filtered
