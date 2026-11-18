"""A project: one course or subject, with its own files, instructions and chats (Day 18).

Documents and chat sessions point at a project through a nullable project_id; NULL means "no
project", which is what every row created before Day 18 has, so nothing needed a backfill.
"""
import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.db.base import Base

NAME_MAX_LENGTH = 80
DESCRIPTION_MAX_LENGTH = 500
INSTRUCTIONS_MAX_LENGTH = 4000


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(NAME_MAX_LENGTH), nullable=False)
    description = Column(Text, nullable=True)
    # User-written text: it reaches the model only inside the final user turn, fenced (G5, CO4).
    instructions = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    # Archived projects take no new uploads or chats; their existing chats keep working.
    archived_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # Archived projects keep their name, so unarchiving can never produce a duplicate. The
        # constraint's leading user_id also serves "this user's projects" lookups.
        UniqueConstraint("user_id", "name", name="uq_projects_user_id_name"),
    )
