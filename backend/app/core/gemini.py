"""The one place a google.genai client is built.

Each Client costs ~3 s to construct on the dev host (Day 8), so the app builds one in its
lifespan and passes it to every consumer instead of each class building its own.
"""
from google import genai

from app.core.config import settings


def build_gemini_client() -> genai.Client:
    api_key = settings.GEMINI_API_KEY.get_secret_value()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)
