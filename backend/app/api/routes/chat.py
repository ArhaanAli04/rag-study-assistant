from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_services, get_user_from_query_token
from app.db.database import User
from app.services.container import Services

router = APIRouter(tags=["Chat"])


@router.get("/chat/stream")
async def chat_stream(
    query: str,
    session_id: int = 0,
    top_k: int = 5,
    mode: str = "quick",
    current_user: User = Depends(get_user_from_query_token),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> StreamingResponse:
    """The SSE answer stream (event order in app/services/chat_pipeline.py). The JWT comes as
    ?token= because EventSource can't send headers."""
    chat = services.chat_pipeline.answer(db, current_user, query, session_id, top_k, mode)
    return StreamingResponse(chat.events, media_type="text/event-stream", headers=chat.headers)
