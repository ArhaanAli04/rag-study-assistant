import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.db.base import Base


class FailedQuery(Base):
    __tablename__ = "failed_queries"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # SET NULL: a failed query outlives its session as analytics (Day 14 found the 500 without it).
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)
    query = Column(Text, nullable=False)
    confidence = Column(Integer, nullable=True)  # 0-100 scale
    feedback = Column(String, nullable=True)  # "down"
    reason = Column(String, nullable=True)  # "low_confidence" or "negative_feedback"
    comment = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
