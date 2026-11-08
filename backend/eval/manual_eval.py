"""
Spot-check hybrid retrieval for the first user in the database.

Run from backend/: python -m eval.manual_eval (needs the real .env, Gemini and Redis).
It searches the in-memory indexes of this process only (I4), so it finds nothing unless documents
were indexed in the same process. Day 11's retrieval harness replaces it.
"""
from app.db.database import SessionLocal, User
from app.retrieval.retrieval_service import RetrievalService
from app.services.container import build_services

queries = [
    ("supervised learning", [5]),
    ("confusion matrix", [5]),
    ("cross validation", [5]),
]

def run_queries(retrieval_service: RetrievalService) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).first()
        user_id = str(user.id)
        doc_version = user.doc_version
    finally:
        db.close()

    for query, expected_docs in queries:
        result = retrieval_service.hybrid_retrieve(query, user_id, doc_version, top_k=5)
        retrieved = [c["metadata"].get("document_id") for c in result["results"]]
        hit = any(d in expected_docs for d in retrieved)
        print(f"'{query}' -> retrieved: {retrieved[:3]} -> HIT: {hit}")

def main() -> None:
    services = build_services()
    try:
        run_queries(services.retrieval_service)
    finally:
        services.close()

if __name__ == "__main__":
    main()
