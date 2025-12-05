"""
RAG-specific evaluation metrics using RAGAS library.
Faithfulness, Answer Relevancy, Context Recall, Context Precision.
"""
import os
from typing import List, Dict, Any
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness, 
    answer_relevancy, 
    context_recall, 
    context_precision
)
from llm_client import LLMClient
from main import llm_client  # reuse your existing client

class RAGEvaluator:
    def __init__(self):
        self.llm_client = llm_client
        # RAGAS needs OpenAI-style client, we'll wrap Gemini
        os.environ["OPENAI_API_KEY"] = "dummy"  # RAGAS doesn't use real key with custom LLM
    
    def evaluate_batch(self, eval_data: List[Dict[str, str]]) -> Dict[str, float]:
        """
        eval_data format:
        [
            {
                "question": "What is overfitting?",
                "answer": "Overfitting occurs when...",
                "contexts": ["Chunk 1 text", "Chunk 2 text"],  # retrieved chunks
                "ground_truth": "Ground truth answer from your docs"
            }
        ]
        """
        dataset = Dataset.from_list(eval_data)
        
        result = evaluate(
            dataset,
            metrics=[
                faithfulness,
                answer_relevancy, 
                context_recall,
                context_precision
            ],
            llm=self.llm_client,  # your Gemini client
        )
        
        return {
            "faithfulness": result["faithfulness"],
            "answer_relevancy": result["answer_relevancy"],
            "context_recall": result["context_recall"],
            "context_precision": result["context_precision"],
        }

# Manual fallback metrics (if RAGAS has issues)
def manual_faithfulness(question: str, answer: str, contexts: List[str]) -> float:
    """Simple heuristic: % of answer words appearing in contexts."""
    context_words = set()
    for ctx in contexts:
        context_words.update(ctx.lower().split())
    
    answer_words = set(answer.lower().split())
    overlap = len(answer_words & context_words) / len(answer_words) if answer_words else 0
    return overlap

def manual_relevancy(question: str, answer: str) -> float:
    """Keyword overlap between question and answer."""
    q_words = set(question.lower().split())
    a_words = set(answer.lower().split())
    return len(q_words & a_words) / len(q_words) if q_words else 0
