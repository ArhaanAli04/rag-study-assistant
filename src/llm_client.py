from typing import List, Dict,AsyncGenerator
from google import genai  # [web:91][web:94]
from dotenv import load_dotenv
import os
import time
import random

class LLMClient:
    """
    Gemini-based client with a grounded RAG prompt and citation requirements.
    """

    def __init__(self, model_name: str = "gemini-2.5-flash-lite"):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=api_key)
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

    def _call_gemini_with_retry(self, prompt: str, max_retries: int = 3) -> str:
        self._check_circuit()
        last_exc: Exception | None = None

        for attempt in range(max_retries):
            try:
                resp = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                self._record_success()
                return resp.text or ""
            except Exception as e:
                last_exc = e
                self._record_failure()
                # backoff with jitter
                if attempt < max_retries - 1:
                    delay = min(8, 1 * (2 ** attempt)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                else:
                    # all retries failed
                    break

        # After retries, if circuit now open, raise a cleaner error up
        raise RuntimeError(f"LLM call failed after retries: {last_exc}")
    
    def generate_answer(self, prompt: str) -> str:
        
        return self._call_gemini_with_retry(prompt)
    
    def generate_followups(self, question: str, answer: str, mode: str = "detailed") -> List[str]:
        prompt = (
            "You are an AI tutor.\n"
            "Given the user's original question and your answer, propose 2-3 short follow-up questions "
            "that a curious student might ask next to deepen understanding.\n"
            "Return them as a simple numbered list.\n\n"
            f"User question: {question}\n\n"
            f"Your answer: {answer}\n"
        )
        
        text = self._call_gemini_with_retry(prompt)
        lines = [l.strip("- ").strip() for l in text.split("\n") if l.strip()]
        return [l for l in lines if len(l) > 0][:3]
    
    def verify_answer(self, question: str, answer: str, sources: List[Dict]) -> str:
        # build a compact source summary
        src_text = ""
        for s in sources[:8]:
            if "url" in s:
                src_text += f"- Web: {s.get('url')}\n"
            else:
                src_text += f"- Local: {s.get('file_name','')} page {s.get('page_num')}\n"

        prompt = (
            "You are a careful verifier.\n"
            "Given a user's question, an AI-generated answer, and a list of sources, "
            "check whether the answer is fully supported by the sources.\n"
            "If the answer contains unsupported claims, point them out briefly.\n"
            "Respond in 2–4 sentences.\n\n"
            f"Question: {question}\n\n"
            f"Answer: {answer}\n\n"
            f"Sources list:\n{src_text}\n"
        )
        return self._call_gemini_with_retry(prompt)
    
    def stream_answer(self, prompt: str) :
        """
        Stream tokens from Gemini and yield them one by one.
        """
        self._check_circuit()
        
        try:
            
            response =  self.client.models.generate_content_stream(
                model=self.model_name,
                contents=[prompt],
                
            )
            
            self._record_success()
            for chunk in response:
                text = getattr(chunk, "text", None)
                if text:
                    # Yield text chunks to FastAPI StreamingResponse
                    yield text
                    
        except Exception as e:
            self._record_failure()
            raise RuntimeError(f"Streaming LLM call failed: {e}")
