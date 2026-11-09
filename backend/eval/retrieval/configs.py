"""Named retrieval configurations. `baseline` is production's retrieval with web search off."""
from dataclasses import dataclass
from typing import Dict

# ChatWindow.js sends top_k=5, and chat asks hybrid_retrieve for RERANK_TOP_K = 5 results.
SERVED_TOP_K = 5
DEEP_TOP_K = 10


@dataclass(frozen=True)
class RetrievalConfig:
    name: str
    description: str
    vector_weight: float = 0.6
    keyword_weight: float = 0.4
    web_search_enabled: bool = False


CONFIGS: Dict[str, RetrievalConfig] = {
    config.name: config
    for config in (
        RetrievalConfig("baseline", "production fusion (0.6 vector / 0.4 BM25), web off"),
        RetrievalConfig("vector_only", "vector half alone (1.0 / 0.0), web off", 1.0, 0.0),
        RetrievalConfig("keyword_only", "BM25 half alone (0.0 / 1.0), web off", 0.0, 1.0),
        RetrievalConfig(
            "web", "production fusion with Tavily on: where the flat 0.5 web score lands",
            web_search_enabled=True,
        ),
    )
}
