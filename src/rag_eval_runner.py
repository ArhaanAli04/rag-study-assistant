"""
Run RAGAS + manual metrics on sample data or real chat logs.
"""
from rag_metrics import RAGEvaluator, manual_faithfulness, manual_relevancy
from sample_eval_data import get_sample_data
from main import retrieval_service
from db import SessionLocal, User

def run_ragas_eval():
    """Run full RAGAS evaluation."""
    evaluator = RAGEvaluator()
    data = get_sample_data()
    
    print("=== RAGAS Metrics ===")
    try:
        results = evaluator.evaluate_batch(data)
        for metric, score in results.items():
            print(f"{metric}: {score:.3f}")
    except Exception as e:
        print(f"RAGAS failed: {e}")
        print("Falling back to manual metrics...")

def run_manual_metrics():
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

def test_retrieval_recall(query: str, expected_doc_id: int):
    """Test if retrieval finds expected document."""
    db = SessionLocal()
    try:
        user = db.query(User).first()
        result = retrieval_service.hybrid_retrieve(
            query, str(user.id), user.doc_version, top_k=5
        )
        retrieved_ids = [c["metadata"].get("document_id") for c in result["results"]]
        found = expected_doc_id in retrieved_ids
        print(f"Query: '{query}' → Retrieved: {retrieved_ids[:3]} → Found doc {expected_doc_id}: {found}")
    finally:
        db.close()

if __name__ == "__main__":
    print("Running Day 16 RAG Evaluation...")
    run_ragas_eval()
    run_manual_metrics()
    
    print("\n=== Retrieval Recall Test ===")
    test_retrieval_recall("overfitting", 1)  # test_doc1.pdf
    test_retrieval_recall("confusion matrix", 1)
