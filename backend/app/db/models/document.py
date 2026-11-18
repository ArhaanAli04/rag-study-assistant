import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


# Versioning: a new file name or hash creates a new version of (user_id, project_id, file_name);
# services/document_service.py decides which. The project is part of the key (Day 18, Decision 2A):
# courses reuse file names ("Unit 1.pdf"), and one course's file must not supersede another's.
class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # NULL = no project. SET NULL is the safety net; deleting a project deletes or unassigns its
    # documents explicitly first (services/project_service.py).
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_hash = Column(String, nullable=False)
    # Bytes, stored at upload: the file itself may live in object storage, not on this disk.
    file_size = Column(Integer, nullable=True)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="documents")

    __table_args__ = (
        # Searches filter documents by (user_id, project_id) through their join (Decision 3A).
        Index("ix_documents_user_id_project_id", "user_id", "project_id"),
    )
