from typing import Optional

from pydantic import BaseModel


class FeedbackRequest(BaseModel):
    feedback: str              # "up" or "down"
    comment: Optional[str] = None
