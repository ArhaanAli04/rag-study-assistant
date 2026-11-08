"""Quiz generation: one Gemini prompt from the topic alone (general knowledge, not the user's documents)."""
from app.generation.llm_client import LLMClient

DIFFICULTY_INSTRUCTIONS = {
    "easy": "basic, straightforward questions suitable for beginners",
    "medium": "moderate difficulty questions requiring understanding of key concepts",
    "hard": "advanced, challenging questions requiring deep understanding and critical thinking",
}


def build_quiz_prompt(topic: str, num_questions: int, difficulty: str, include_answers: bool) -> str:
    difficulty_desc = DIFFICULTY_INSTRUCTIONS[difficulty]

    if include_answers:
        return f"""You are an expert quiz creator. Generate {num_questions} multiple-choice questions about "{topic}".

Difficulty Level: {difficulty.upper()} - Create {difficulty_desc}.
IMPORTANT: Use plain text only. Do NOT use markdown formatting (no **, ##, or other symbols).

Format each question EXACTLY like this:

Question X: [question text]
A) [option A]
B) [option B]
C) [option C]
D) [option D]
Correct Answer: [letter]
Explanation: [brief explanation]

Make the questions educational and accurate. Include varied topics within {topic}."""

    return f"""You are an expert quiz creator. Generate {num_questions} multiple-choice questions about "{topic}".

Difficulty Level: {difficulty.upper()} - Create {difficulty_desc}.
IMPORTANT: Use plain text only. Do NOT use markdown formatting (no **, ##, or other symbols).

Format each question as:
Question X: [question text]
A) [option A]
B) [option B]
C) [option C]
D) [option D]

Question 2: [question text]
A) [option A]
B) [option B]
C) [option C]
D) [option D]

Do NOT include answers. Make the questions educational and accurate."""


def generate_quiz_text(
    llm_client: LLMClient, topic: str, num_questions: int, difficulty: str, include_answers: bool
) -> str:
    """Plain quiz text from Gemini. Raises RuntimeError when the LLM call fails (retries exhausted
    or the circuit breaker is open); the route turns that into a 503."""
    prompt = build_quiz_prompt(topic, num_questions, difficulty, include_answers)
    return llm_client.generate_answer({"current_user_text": prompt, "contents": []})
