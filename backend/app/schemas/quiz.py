from enum import Enum

from pydantic import BaseModel


class QuizDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class QuizRequest(BaseModel):
    topic: str
    num_questions: int = 5
    difficulty: QuizDifficulty = QuizDifficulty.MEDIUM
    include_answers: bool = False  # True if you want answers
