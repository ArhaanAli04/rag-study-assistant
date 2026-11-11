import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    username = Column(String, nullable=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    profile_picture = Column(String, nullable=True)  # From Google
    oauth_provider = Column(String, nullable=True)  # "google" or None
    is_active = Column(Boolean, default=True)
    doc_version = Column(Integer, default=0)  # increments on document upload

    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
