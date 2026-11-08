import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_services
from app.db.database import User
from app.schemas.quiz import QuizRequest
from app.services.container import Services
from app.services.quiz_service import generate_quiz_text

logger = logging.getLogger("rag_assistant.api.quiz")
router = APIRouter(tags=["Quiz"])


@router.post("/quiz")
async def generate_quiz(
    body: QuizRequest,
    current_user: User = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    """Generate quiz questions from internet knowledge (not user documents)"""
    logger.info(f"Generating {body.difficulty} quiz for user {current_user.id}, topic: {body.topic}")
    try:
        quiz_text = generate_quiz_text(
            services.llm_client, body.topic, body.num_questions, body.difficulty.value, body.include_answers
        )
    except RuntimeError as e:
        logger.error(f"LLM error in /quiz: {e}")
        raise HTTPException(
            status_code=503,
            detail="Quiz generation service is temporarily unavailable."
        )

    return {
        "topic": body.topic,
        "difficulty": body.difficulty,
        "num_questions": body.num_questions,
        "questions": quiz_text,
        "has_answers": body.include_answers,
    }
