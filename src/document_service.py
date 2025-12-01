#versioning logic
from db import SessionLocal, Document
from utils_file import compute_file_hash

def register_document(user_id: str, file_path: str) -> Document:
    db = SessionLocal()
    file_name = file_path.split("/")[-1].split("\\")[-1]
    file_hash = compute_file_hash(file_path)

    existing = (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.file_name == file_name)
        .order_by(Document.version.desc())
        .first()
    )

    if existing and existing.file_hash == file_hash:
        # Same file re-uploaded: keep version, maybe skip reindexing
        return existing

    new_version = 1
    if existing:
        existing.is_active = False
        db.add(existing)
        new_version = existing.version + 1

    doc = Document(
        user_id=user_id,
        file_name=file_name,
        file_path=file_path,
        file_hash=file_hash,
        version=new_version,
        is_active=True,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    db.close()
    return doc
