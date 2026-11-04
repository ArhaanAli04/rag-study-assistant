from index_builder import IndexBuilder
from retrieval_service import RetrievalService
from vector_store import FaissVectorStore

def main():
    # Load existing index (built earlier)
    vs = FaissVectorStore(embedding_dim=384)  # MiniLM dim
    vs.load("data/faiss_index.bin", "data/faiss_metadata.json")

    ib = IndexBuilder()
    ib.vector_store = vs  # reuse loaded store
    rs = RetrievalService(ib)

    queries = [
        "What are morphemes?",
        "What does the slide say about transformers?",
        "what is covered in the docx file?."
    ]

    for k in [3, 5]:
        print(f"\n=== top_k = {k} ===")
        for q in queries:
            print(f"\nQuery: {q}")
            results = rs.semantic_search(q, user_id=None, top_k=k)
            for r in results:
                meta = r["metadata"]
                print(f"- score={r['score']:.4f}, type={meta['doc_type']}, file={meta['file_name']}")
                print("  preview:", meta["text"][:160].replace("\n", " "), "...\n")

if __name__ == "__main__":
    main()
