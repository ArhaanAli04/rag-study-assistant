"""Request and response bodies of the projects API (Day 18)."""
import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.db.models.project import DESCRIPTION_MAX_LENGTH, INSTRUCTIONS_MAX_LENGTH, NAME_MAX_LENGTH

# What deleting a project does with its documents; the client must say (no default).
DocumentsOnDelete = Literal["delete", "unassign"]


def _clean_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("Project name cannot be empty")
    return name


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    """An emptied description or instructions box is stored as no value, not as whitespace."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ProjectCreate(BaseModel):
    name: str = Field(max_length=NAME_MAX_LENGTH)
    description: Optional[str] = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    instructions: Optional[str] = Field(default=None, max_length=INSTRUCTIONS_MAX_LENGTH)

    _name = field_validator("name")(_clean_name)
    _texts = field_validator("description", "instructions")(_blank_to_none)


class ProjectUpdate(BaseModel):
    """Only the fields sent are changed; `archived` sets or clears archived_at."""

    name: Optional[str] = Field(default=None, max_length=NAME_MAX_LENGTH)
    description: Optional[str] = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    instructions: Optional[str] = Field(default=None, max_length=INSTRUCTIONS_MAX_LENGTH)
    archived: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _clean_name(value)

    _texts = field_validator("description", "instructions")(_blank_to_none)


class ProjectOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    instructions: Optional[str]
    created_at: datetime.datetime
    archived: bool
    document_count: int
    chat_count: int
    last_activity: Optional[datetime.datetime]


class ProjectDocumentOut(BaseModel):
    id: int
    filename: str
    version: int
    created_at: Optional[datetime.datetime]
    chunks: int


class ProjectChatOut(BaseModel):
    id: int
    title: Optional[str]
    topic: str
    created_at: Optional[datetime.datetime]
    last_message_time: Optional[datetime.datetime]


class ProjectDetailOut(ProjectOut):
    documents: List[ProjectDocumentOut]
    chats: List[ProjectChatOut]


class ProjectDeletedOut(BaseModel):
    status: Literal["deleted"]
    project_id: int
    documents: DocumentsOnDelete
    documents_deleted: int
    documents_unassigned: int
    chats_unassigned: int
    doc_version: int


class MoveToProject(BaseModel):
    """Move a document or a chat: a project id of the user's, or null for no project."""

    project_id: Optional[int]
