"""Every ORM model, imported in one place.

Importing this package registers all tables on Base.metadata. alembic/env.py imports it, so
autogenerate sees every table; a model missing here would look deleted and get a drop_table (T2).
"""
from app.db.models.chat_session import Session
from app.db.models.concept_map import ConceptMap, ConceptMapNode
from app.db.models.document import Document
from app.db.models.document_chunk import Chunk
from app.db.models.failed_query import FailedQuery
from app.db.models.message import Message
from app.db.models.user import User

__all__ = ["Chunk", "ConceptMap", "ConceptMapNode", "Document", "FailedQuery", "Message", "Session", "User"]
