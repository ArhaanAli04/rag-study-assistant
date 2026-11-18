import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


# Named Session for the existing callers (`Session as ChatSession`); the file name avoids
# confusion with db/session.py, which holds the engine and SQLAlchemy's session factory.
class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # NULL = no project: the chat searches the user's unassigned documents (Day 18, Decision 1A).
    # Set when the session is created; moved only by an explicit PATCH. A deleted project's chats
    # move to no project (Decision 4A).
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String, nullable=True)
    topic = Column(String, nullable=True, default="General")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
