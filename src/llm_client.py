from typing import List, Dict
from google import genai  # [web:91][web:94]
from dotenv import load_dotenv
import os

class LLMClient:
    """
    Gemini-based client with a grounded RAG prompt and citation requirements.
    """

    def __init__(self, model_name: str = "gemini-2.0-flash"):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def build_prompt(
        self,
        question: str,
        context_chunks: List[Dict],
        recent_messages: List[Dict],
        grounding_level: str = "strict",  # can be: "strict", "loose", "none"
    ) -> str:
        """
        Build a single text prompt for Gemini:
        - Includes system-like instructions at top
        - Includes recent chat history
        - Includes retrieved context with provenance
        - Asks for citations in [Source: ...] / [Web: ...] form
        """
        if grounding_level == "strict":
            system_instructions = (
                "You are an AI study assistant helping a student...\n"
                "Use ONLY the information contained in the provided context snippets.\n"
                "If the answer is not supported by the context, say you are not sure.\n"
                "Cite sources inline as [Source: filename, Page X] or [Web: URL].\n"
                "Answer clearly, concisely, and do not hallucinate.\n"
            )
        elif grounding_level == "loose":
            system_instructions = (
                "You are an AI assistant. Use the context snippets primarily, but if the "
                "context is insufficient, you may rely on your general knowledge.\n"
                "Cite sources when possible.\n"
                "Avoid guessing when unsure.\n"
            )
        else:  # grounding_level == "none"
            system_instructions = (
                "You are an AI assistant answering freely without grounding constraints.\n"
                "You may use your general knowledge to answer any question.\n"
            )
        

        # Conversation history
        history_lines = []
        for m in recent_messages[::-1]:  # reverse to chronological
            role = "User" if m["role"] == "user" else "Assistant"
            history_lines.append(f"{role}: {m['content']}")
        history_block = "\n".join(history_lines)

        # Context with provenance
        context_lines = []
        for c in context_chunks:
            meta = c["metadata"]
            source_type = meta.get("source_type", "local")
            if source_type == "web":
                src = f"Web URL: {meta.get('url', '')}"
            else:
                page = meta.get("page_num") or meta.get("parent_page")
                src = f"Local file: {meta.get('file_name', '')}, Page {page}"
            context_lines.append(f"[CONTEXT FROM {src}]\n{c['text']}")
        context_block = "\n\n".join(context_lines)

        prompt = (
            f"{system_instructions}\n"
            f"Conversation so far:\n{history_block}\n\n"
            f"Context snippets:\n{context_block}\n\n"
            f"User question: {question}\n\n"
            "Now produce the best possible answer following the citation rules."
        )
        return prompt

    def generate_answer(self, prompt: str) -> str:
        """
        Call Gemini with the constructed prompt and return plain text. [web:91][web:94]
        """
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        # .text flattens parts to a single string. [web:91][web:93]
        return response.text or ""
