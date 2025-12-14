from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text,Boolean
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import datetime
import os

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    doc_version = Column(Integer, default=0)  # increments on document upload

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    title = Column(String, nullable=True)
    topic = Column(String, nullable=True, default="General")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

    messages = relationship("Message", back_populates="session")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    sources = Column(Text, nullable=True)
    # NEW: feedback fields
    feedback = Column(String, nullable=True)          # "up" / "down"
    feedback_comment = Column(Text, nullable=True)    # optional free-text comment
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("Session", back_populates="messages")

#document versioning-versioning strategy: store document hashes and version numbers in the SQL DB; if a hash already exists for the same user/file_name, increment version and (optionally) remove old chunks.

from sqlalchemy import Boolean

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_hash = Column(String, nullable=False)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)

class FailedQuery(Base):
    __tablename__ = "failed_queries"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    query = Column(Text, nullable=False)
    confidence = Column(Integer, nullable=True)  # 0-100 scale
    feedback = Column(String, nullable=True)  # "down"
    reason = Column(String, nullable=True)  # "low_confidence" or "negative_feedback"
    comment = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

engine = create_engine(f"sqlite:///{DATA_DIR}/app.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def refresh_metadata():
    """Force SQLAlchemy to reload table metadata from database"""
    Base.metadata.clear()
    Base.metadata.reflect(bind=engine)

