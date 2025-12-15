from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text,Boolean
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import datetime
import os
import sqlite3
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=True)  
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
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

def migrate_database():
    """Apply database migrations"""
    db_path = f"{DATA_DIR}/app.db"
    
    if not os.path.exists(db_path):
        return  # No database yet, will be created fresh
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            return  # Table doesn't exist yet
        
        # Get current columns
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Add missing columns
        if 'name' not in columns:
            print("🔧 Adding 'name' column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN name VARCHAR")
            conn.commit()
            print("✅ Added 'name' column")
        
        if 'created_at' not in columns:
            print("🔧 Adding 'created_at' column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN created_at DATETIME")
            # Set current timestamp for existing users
            cursor.execute("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
            conn.commit()
            print("✅ Added 'created_at' column")
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()
def init_db():
    Base.metadata.create_all(bind=engine)
    # Then apply migrations to existing tables
    migrate_database()

def refresh_metadata():
    """Force SQLAlchemy to reload table metadata from database"""
    Base.metadata.clear()
    Base.metadata.reflect(bind=engine)

