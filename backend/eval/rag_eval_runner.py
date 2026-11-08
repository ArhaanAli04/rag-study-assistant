"""
Run RAGAS + manual metrics on sample data or real chat logs.

Run from backend/: python -m eval.rag_eval_runner (needs the real .env, Gemini and Redis).
The retrieval check searches the in-memory indexes of this process only (I4), so it finds nothing
unless documents were indexed in the same process. Days 11-12 replace this script.
"""
from app.generation.llm_client import LLMClient
from app.retrieval.retrieval_service import RetrievalService
from app.services.container import build_services
from eval.rag_metrics import RAGEvaluator, manual_faithfulness, manual_relevancy
from eval.sample_eval_data import get_sample_data
from app.db.database import SessionLocal, User

def run_ragas_eval(llm_client: LLMClient) -> None:
    """Run full RAGAS evaluation."""
    evaluator = RAGEvaluator(llm_client)
    data = get_sample_data()

    print("=== RAGAS Metrics ===")
    try:
        results = evaluator.evaluate_batch(data)
        for metric, score in results.items():
            print(f"{metric}: {score:.3f}")
    except Exception as e:
        print(f"RAGAS failed: {e}")
        print("Falling back to manual metrics...")

def run_manual_metrics() -> None:
    """Manual fallback metrics."""
    data = get_sample_data()
    print("\n=== Manual Metrics ===")

    for i, item in enumerate(data):
        faithfulness_score = manual_faithfulness(
            item["question"], item["answer"], item["contexts"]
        )
        relevancy_score = manual_relevancy(item["question"], item["answer"])

        print(f"Q{i+1}: Faithfulness={faithfulness_score:.3f}, Relevancy={relevancy_score:.3f}")
        print(f"  Q: {item['question'][:60]}...")
        print(f"  A: {item['answer'][:60]}...")

def test_retrieval_recall(retrieval_service: RetrievalService, query: str, expected_doc_id: int) -> None:
    """Test if retrieval finds expected document."""
    db = SessionLocal()
    try:
        user = db.query(User).first()
        result = retrieval_service.hybrid_retrieve(
            query, str(user.id), user.doc_version, top_k=5
        )
        retrieved_ids = [c["metadata"].get("document_id") for c in result["results"]]
        found = expected_doc_id in retrieved_ids
        print(f"Query: '{query}' -> Retrieved: {retrieved_ids[:3]} -> Found doc {expected_doc_id}: {found}")
    finally:
        db.close()

def main() -> None:
    services = build_services()
    try:
        print("Running RAG Evaluation...")
        run_ragas_eval(services.llm_client)
        run_manual_metrics()

        print("\n=== Retrieval Recall Test ===")
        test_retrieval_recall(services.retrieval_service, "overfitting", 1)  # test_doc1.pdf
        test_retrieval_recall(services.retrieval_service, "confusion matrix", 1)
    finally:
        services.close()

if __name__ == "__main__":
    main()
