"""The retrieval confidence scale and every threshold compared against it (B2).

Confidence is 0–100. Comparing it against 0–1 literals is how B2 happened (0.7 / 0.3 grounding
on POST /chat, a 0.3 forced-web cap), so code compares only against these names. The values are
unvalidated heuristics until the retrieval eval harness (E4, Day 11) measures them.
"""
from typing import Literal

CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 100.0

# Below this, retrieval asks Tavily for 3 web results instead of 2.
WEB_FALLBACK_BELOW = 60.0
# When the keyword / example heuristic says the documents don't cover the query, confidence is
# held at or below this so the web fallback above always applies.
FORCED_WEB_CAP = 30.0
# Below this, a final top-k that contains web chunks gets a score in the web range instead.
WEB_RESCORE_BELOW = 40.0
WEB_CONFIDENCE_FLOOR = 40.0
WEB_CONFIDENCE_CEILING = 75.0

GROUNDING_STRICT_MIN = 70.0
GROUNDING_LOOSE_MIN = 30.0
# Answers below this are logged to failed_queries for later analysis.
LOW_CONFIDENCE_BELOW = 30.0

GroundingLevel = Literal["strict", "loose", "none"]


def grounding_level(confidence: float) -> GroundingLevel:
    if confidence >= GROUNDING_STRICT_MIN:
        return "strict"
    if confidence >= GROUNDING_LOOSE_MIN:
        return "loose"
    return "none"
