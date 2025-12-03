from typing import List, Dict
from google import genai  # [web:91][web:94]
from dotenv import load_dotenv
import os

class LLMClient:
    """
    Gemini-based client with a grounded RAG prompt and citation requirements.
    """

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def _mode_instructions(self, mode: str) -> str:
        mode = (mode or "detailed").lower()
        if mode == "quick":
            return (
                "Answer briefly in 3 to 5 sentences focusing only on the key points.\n"
                "Avoid long explanations unless strictly necessary.\n"
            )
        elif mode == "step_by_step":
            return (
                "Explain your reasoning in clear, numbered steps.\n"
                "Start from definitions or assumptions, then proceed step by step "
                "until you reach the final answer.\n"
            )
        # default: detailed
        return (
            "Provide a detailed explanation with enough depth for a student to understand the concept clearly.\n"
            "Include definitions, key properties or features, and, when helpful, small examples.\n"
            "Also provide advantages or benefits, disadvantages or limitations, and comparisons if relevant.\n"
            "Provide applications or use cases if there are any.\n"
        )
    def build_prompt(
        self,
        question: str,
        context_chunks: List[Dict],
        recent_messages: List[Dict],
        grounding_level: str = "strict",  # can be: "strict", "loose", "none"
        mode: str = "detailed",
    ) -> str:
        """
        Build a single text prompt for Gemini:
        - Includes system-like instructions at top
        - Includes recent chat history
        - Includes retrieved context with provenance
        - Asks for citations in [Source: ...] / [Web: ...] form
        """
        if grounding_level == "strict":
            grounding_instructions = (
                "You are an AI study assistant helping a student...\n"
                "Use ONLY the information contained in the provided context snippets.\n"
                "If the context does not mention the topic at all, reply exactly like this:\n"
                "\"I am not sure because the provided context does not contain information about this question.\"\n"
                "If the context partially mentions the topic but does not fully answer it, clearly state what is known and what is unknown.\n"
                "Cite sources from local documents as [Source: filename, Page X] or [Web: URL] when it comes from a web page.\n"
                "Answer clearly, concisely, and do not hallucinate.\n"
            )
        elif grounding_level == "loose":
            grounding_instructions = (
                "You are an AI study assistant.\n"
                "Primarily rely on the provided context snippets, but if they are insufficient, "
                "you may use your general knowledge.\n"
                "Cite local documents as [Source: filename, Page X] and web pages as [Web: URL] whenever possible.\n"
                "Avoid obvious guessing; if you are uncertain, say so clearly.\n"
            )
        else:  # grounding_level == "none"
            grounding_instructions = (
                "You are an AI study assistant.\n"
                "You may use your general knowledge freely, without being limited to the context snippets.\n"
                "If you use information that clearly comes from a source in the context, you may still cite it.\n"
            )
        mode_instructions = self._mode_instructions(mode)

        system_instructions = (
            grounding_instructions +
            mode_instructions +
            "Use clear language suitable for a student.\n"
            "Avoid copying long passages verbatim from the context; paraphrase instead.\n"
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
    
    def generate_followups(self, question: str, answer: str, mode: str = "detailed") -> List[str]:
        prompt = (
            "You are an AI tutor.\n"
            "Given the user's original question and your answer, propose 2-3 short follow-up questions "
            "that a curious student might ask next to deepen understanding.\n"
            "Return them as a simple numbered list.\n\n"
            f"User question: {question}\n\n"
            f"Your answer: {answer}\n"
        )
        resp = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        text = resp.text or ""
        lines = [l.strip("- ").strip() for l in text.split("\n") if l.strip()]
        return [l for l in lines if len(l) > 0][:3]
