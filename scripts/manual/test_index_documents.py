import os

from chunk_builder import (
    build_chunks_from_pdf,
    build_chunks_from_pptx,
    build_chunks_from_docx,
)
from index_builder import IndexBuilder


def main():
    # 1) Paths to test files
    pdf_path = "uploads/B11-02-NLP Exp4.pdf"
    pptx_path = "uploads/sample1.pptx"
    docx_path = "uploads/test_style.docx"

    chunks = []

    # 2) PDF chunks
    if os.path.exists(pdf_path):
        pdf_chunks = build_chunks_from_pdf(pdf_path, subject_tags="nlp,notes")
        print(f"PDF: built {len(pdf_chunks)} chunks from {pdf_path}")
        chunks.extend(pdf_chunks)
    else:
        print("PDF not found:", pdf_path)

    # 3) PPTX chunks
    if os.path.exists(pptx_path):
        pptx_chunks = build_chunks_from_pptx(pptx_path, subject_tags="slides,lecture")
        print(f"PPTX: built {len(pptx_chunks)} chunks from {pptx_path}")
        chunks.extend(pptx_chunks)
    else:
        print("PPTX not found:", pptx_path)

    # 4) DOCX chunks
    if os.path.exists(docx_path):
        docx_chunks = build_chunks_from_docx(docx_path, subject_tags="docx,notes")
        print(f"DOCX: built {len(docx_chunks)} chunks from {docx_path}")
        chunks.extend(docx_chunks)
    else:
        print("DOCX not found:", docx_path)

    if not chunks:
        print("No documents found to index. Add test files in uploads/ and rerun.")
        return

    # 5) Build index
    index_builder = IndexBuilder()
    index_builder.index_chunks(chunks, batch_size=32)

    # 6) Optional: save index
    vs = index_builder.get_index()
    vs.save("data/faiss_index.bin", "data/faiss_metadata.json")

    # 7) (Optional) Load into a fresh store to verify persistence
    from vector_store import FaissVectorStore
    loaded_store = FaissVectorStore(embedding_dim=vs.embedding_dim)
    loaded_store.load("data/faiss_index.bin", "data/faiss_metadata.json")
    # 7) Test queries hitting all types
    queries = [
        "What is Morphemes?",
        "What does the slide say about transformers?",
        "What is covered in the docx notes?",
    ]

    for q in queries:
        print(f"\nQuery: {q}")
        # embed query using the same embedding service
        query_emb = index_builder.embedding_service.embed_texts([q])[0]
        results = loaded_store.search(query_emb, top_k=3)
        
        for dist, meta in results:
            print(f"- score={dist:.4f}, type={meta['doc_type']}, file={meta['file_name']}, page/slide={meta['page_num']}")
            print("  preview:", meta["text"][:160].replace("\n", " "), "...\n")


if __name__ == "__main__":
    main()
