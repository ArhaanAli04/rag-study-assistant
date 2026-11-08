from typing import List, Dict
from google import genai
from google.genai import types as genai_types
import time
import random

class LLMClient:
    """
    Gemini-based client with a grounded RAG prompt and citation requirements.
    Uses native multi-turn conversation format for proper memory across turns.
    """

    def __init__(self, client: genai.Client, model_name: str = "gemini-2.5-flash-lite") -> None:
        self.client = client
        self.model_name = model_name
        # circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_open_until = 0.0  # epoch seconds

    def _check_circuit(self):
        now = time.time()
        if self._circuit_open and now < self._circuit_open_until:
            raise RuntimeError("LLM circuit breaker is open; temporarily refusing calls.")
        if self._circuit_open and now >= self._circuit_open_until:
            # half-open: allow one call
            self._circuit_open = False
            self._consecutive_failures = 0

    def _record_success(self):
        self._consecutive_failures = 0

    def _record_failure(self, max_failures: int = 3, open_seconds: int = 60):
        self._consecutive_failures += 1
        if self._consecutive_failures >= max_failures:
            self._circuit_open = True
            self._circuit_open_until = time.time() + open_seconds

    def _mode_instructions(self, mode: str) -> str:
        # The frontend sends "step-by-step"; /chat's documented value is "step_by_step".
        mode = (mode or "detailed").lower().replace("-", "_")
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
    def _build_system_instruction(
        self,
        grounding_level: str,
        mode: str,
    ) -> str:
        """Build the system instruction string for the Gemini config."""
        if grounding_level == "strict":
            grounding_instructions = (
                "You are an AI study assistant helping a student.\n"
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
        else:
            grounding_instructions = (
                "You are an AI study assistant.\n"
                "You may use your general knowledge freely, without being limited to the context snippets.\n"
                "If you use information that clearly comes from a source in the context, you may still cite it.\n"
            )
        return (
            grounding_instructions
            + self._mode_instructions(mode)
            + "Use clear language suitable for a student.\n"
            "Avoid copying long passages verbatim from the context; paraphrase instead.\n"
            "You have access to the full conversation history above — use it to resolve pronouns, "
            "follow-up references, and context from earlier turns.\n"
        )

    def build_prompt(
        self,
        question: str,
        context_chunks: List[Dict],
        recent_messages: List[Dict],
        grounding_level: str = "strict",
        mode: str = "detailed",
    ) -> Dict:
        """
        Build a multi-turn conversation payload for Gemini.

        Returns a dict with keys:
          - 'contents': list of {role, parts} objects for prior turns
          - 'current_user_text': the text of the current user turn (injected with context)
          - 'system_instruction': top-level system prompt string

        recent_messages should NOT include the current question — pass only prior turns.
        Messages are expected in chronological order (oldest first).
        """
        system_instruction = self._build_system_instruction(grounding_level, mode)

        # Build context block to attach to the current user turn
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

        # Build prior-turn contents list (role: "user" / "model")
        contents = []
        for m in recent_messages:  # already chronological (oldest first)
            gemini_role = "user" if m["role"] == "user" else "model"
            contents.append({"role": gemini_role, "parts": [{"text": m["content"]}]})

        # Current user turn: attach retrieved context so the model can cite it
        if context_block:
            current_user_text = (
                f"Context snippets:\n{context_block}\n\n"
                f"User question: {question}\n\n"
                "Now produce the best possible answer following the citation rules above."
            )
        else:
            current_user_text = (
                f"User question: {question}\n\n"
                "Produce the best possible answer."
            )

        return {
            "system_instruction": system_instruction,
            "contents": contents,
            "current_user_text": current_user_text,
        }

    def _build_api_contents(self, prompt_payload: Dict) -> tuple:
        """
        Convert the prompt_payload dict into (contents, config) ready for the Gemini API.
        contents is a list of Content objects; config carries the system instruction.
        """
        prior_contents = []
        for turn in prompt_payload.get("contents", []):
            prior_contents.append(
                genai_types.Content(
                    role=turn["role"],
                    parts=[genai_types.Part(text=turn["parts"][0]["text"])],
                )
            )
        # Append the current user turn
        prior_contents.append(
            genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=prompt_payload["current_user_text"])],
            )
        )
        config = genai_types.GenerateContentConfig(
            system_instruction=prompt_payload.get("system_instruction", ""),
        )
        return prior_contents, config

    def _call_gemini_with_retry(self, prompt_payload: Dict, max_retries: int = 3) -> str:
        self._check_circuit()
        last_exc: Exception | None = None

        contents, config = self._build_api_contents(prompt_payload)

        for attempt in range(max_retries):
            try:
                resp = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
                self._record_success()
                return resp.text or ""
            except Exception as e:
                last_exc = e
                self._record_failure()
                if attempt < max_retries - 1:
                    delay = min(8, 1 * (2 ** attempt)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                else:
                    break

        raise RuntimeError(f"LLM call failed after retries: {last_exc}")

    def generate_answer(self, prompt_payload: Dict) -> str:
        return self._call_gemini_with_retry(prompt_payload)
    
    def generate_followups(self, question: str, answer: str, mode: str = "detailed") -> List[str]:
        followup_text = (
            "You are an AI tutor.\n"
            "Given the user's original question and your answer, propose 2-3 short follow-up questions "
            "that a curious student might ask next to deepen understanding.\n"
            "Return them as a simple numbered list.\n\n"
            f"User question: {question}\n\n"
            f"Your answer: {answer}\n"
        )
        # Single-turn call — build a minimal payload
        payload = {
            "system_instruction": "You are a helpful AI tutor.",
            "contents": [],
            "current_user_text": followup_text,
        }
        text = self._call_gemini_with_retry(payload)
        lines = [l.strip("- ").strip() for l in text.split("\n") if l.strip()]
        return [l for l in lines if len(l) > 0][:3]
    
    def verify_answer(self, question: str, answer: str, sources: List[Dict]) -> str:
        src_text = ""
        for s in sources[:8]:
            if "url" in s:
                src_text += f"- Web: {s.get('url')}\n"
            else:
                src_text += f"- Local: {s.get('file_name','')} page {s.get('page_num')}\n"

        verify_text = (
            "You are a careful verifier.\n"
            "Given a user's question, an AI-generated answer, and a list of sources, "
            "check whether the answer is fully supported by the sources.\n"
            "If the answer contains unsupported claims, point them out briefly.\n"
            "Respond in 2–4 sentences.\n\n"
            f"Question: {question}\n\n"
            f"Answer: {answer}\n\n"
            f"Sources list:\n{src_text}\n"
        )
        payload = {
            "system_instruction": "You are a careful verifier.",
            "contents": [],
            "current_user_text": verify_text,
        }
        return self._call_gemini_with_retry(payload)

    def stream_answer(self, prompt_payload: Dict):
        """
        Stream tokens from Gemini using the multi-turn contents format.
        """
        self._check_circuit()

        contents, config = self._build_api_contents(prompt_payload)

        try:
            response = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            self._record_success()
            for chunk in response:
                text = getattr(chunk, "text", None)
                if text:
                    yield text
        except Exception as e:
            self._record_failure()
            raise RuntimeError(f"Streaming LLM call failed: {e}")
