from typing import List, Dict


class LLMClient:
    """
    Placeholder LLM client. Replace 'generate_answer' with real API call (OpenAI, Gemini, etc.).
    """

    def __init__(self):
        pass

    def build_prompt(
        self,
        question: str,
        context_chunks: List[Dict],
        recent_messages: List[Dict],
    ) -> str:
        context_texts = []
        for c in context_chunks:
            meta = c["metadata"]
            src = f"{meta.get('file_name', '')} (p{meta.get('page_num', '')})"
            context_texts.append(f"[SOURCE: {src}]\n{c['text']}")
        context_block = "\n\n".join(context_texts)

        history_lines = []
        for m in recent_messages[::-1]:  # reverse to chronological
            prefix = "User" if m["role"] == "user" else "Assistant"
            history_lines.append(f"{prefix}: {m['content']}")
        history_block = "\n".join(history_lines)

        prompt = (
            "You are an AI study assistant. Use the provided context to answer the user's question.\n\n"
            f"Conversation so far:\n{history_block}\n\n"
            f"Context from documents:\n{context_block}\n\n"
            f"User question: {question}\n\n"
            "Answer clearly and concisely. If the answer is not in the context, say you are not sure."
        )
        return prompt

    def generate_answer(self, prompt: str) -> str:
        # TODO: Replace with real LLM API call.
        # For now, just echo a stub so pipeline can be tested.
        return "LLM response placeholder. Replace LLMClient.generate_answer with a real model call."
