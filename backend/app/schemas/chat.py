from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[int] = None
    top_k: int = 8
    mode: str = "detailed"  # "detailed", "quick", "step_by_step"


class ChatResponse(BaseModel):
    answer: str
    session_id: int
    confidence: float
    fallback_used: bool
    grounding_level: Optional[str] = None  # NEW FIELD
    sources: List[Dict[str, Any]]
    followups: Optional[List[str]] = None
