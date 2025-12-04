from main import retrieval_service
from db import SessionLocal, User

queries = [
    ("supervised learning", [5]),
    ("confusion matrix", [5]),
    ("cross validation", [5]),
]

db = SessionLocal()
user = db.query(User).first()
user_id = str(user.id)
doc_version = user.doc_version

for query, expected_docs in queries:
    result = retrieval_service.hybrid_retrieve(query, user_id, doc_version, top_k=5)
    retrieved = [c["metadata"].get("document_id") for c in result["results"]]
    hit = any(d in expected_docs for d in retrieved)
    print(f"'{query}' → retrieved: {retrieved[:3]} → HIT: {hit}")
