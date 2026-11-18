from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_services, get_user_from_query_token
from app.api.routes.projects import require_project_target
from app.db.models import User
from app.services.container import Services

router = APIRouter(tags=["Chat"])


@router.get("/chat/stream")
def chat_stream(
    query: str,
    session_id: int = 0,
    top_k: int = 5,
    mode: str = "quick",
    project_id: Optional[int] = None,
    current_user: User = Depends(get_user_from_query_token),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> StreamingResponse:
    """The SSE answer stream (event order in app/services/chat_pipeline.py). The JWT comes as
    ?token= because EventSource can't send headers.

    ``project_id`` places a *new* chat in one of the user's projects (Day 18); an existing session
    keeps its own project, so a stale client can't re-scope a chat mid-way. It is checked whenever
    sent: another user's project is a 404 and an archived one a 409, before anything is stored.

    A plain def, with sync event generators: FastAPI runs the pre-stream work in its threadpool and
    Starlette iterates the frames there, so the event loop (and /health) is never blocked (v0.3.1)."""
    project = require_project_target(db, current_user.id, project_id)
    chat = services.chat_pipeline.answer(db, current_user, query, session_id, top_k, mode, project)
    return StreamingResponse(chat.events, media_type="text/event-stream", headers=chat.headers)
