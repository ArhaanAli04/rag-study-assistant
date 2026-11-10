"""Everything between a question and the Gemini call: assemble the context, pick the grounding level
from its confidence, build the prompt.

The chat (services/chat_pipeline.py) and the generation eval (eval/generation/) both call this, so
the eval judges answers to exactly the prompt the chat sends (Day 12, the same pattern as Day 11's
retrieval/context_assembly.py).
"""
from dataclasses import dataclass
from typing import Any, Dict, List

from app.generation.llm_client import LLMClient
from app.retrieval.confidence import grounding_level as grounding_for
from app.retrieval.context_assembly import AssembledContext, assemble_context
from app.retrieval.context_compressor import SimpleContextCompressor
from app.retrieval.query_decomposer import QueryDecomposer
from app.retrieval.retrieval_service import RetrievalService


@dataclass
class PreparedAnswer:
    prompt: Dict[str, Any]
    context: AssembledContext
    grounding_level: str


def prepare_answer(
    retrieval_service: RetrievalService,
    query_decomposer: QueryDecomposer,
    compressor: SimpleContextCompressor,
    llm_client: LLMClient,
    query: str,
    user_id: str,
    doc_version: int,
    top_k: int,
    mode: str,
    recent_messages: List[Dict[str, str]],
) -> PreparedAnswer:
    context = assemble_context(
        retrieval_service, query_decomposer, compressor,
        query=query, user_id=user_id, doc_version=doc_version, top_k=top_k,
    )
    grounding = grounding_for(context.confidence)
    prompt = llm_client.build_prompt(
        question=query,
        context_chunks=context.chunks,
        recent_messages=recent_messages,
        grounding_level=grounding,
        mode=mode,
    )
    return PreparedAnswer(prompt=prompt, context=context, grounding_level=grounding)
