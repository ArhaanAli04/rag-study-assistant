from db import SessionLocal, Document
from vector_store import FaissVectorStore
from keyword_index import BM25KeywordIndex

def delete_document(document_id: int, vs: FaissVectorStore, bm25: BM25KeywordIndex):
    db = SessionLocal()
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        db.close()
        return False

    doc.is_active = False
    db.add(doc)
    db.commit()
    db.close()

    # Mark deleted in vector store
    vs.mark_delete_by_document_id(document_id)

    # For BM25 you can either rebuild later or mark deleted via metadata;
    # since bm25 uses metadata, that 'deleted' flag will be present.
    return True
