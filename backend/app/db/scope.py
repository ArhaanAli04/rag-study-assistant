"""Which of a user's documents a search may return (Day 18): all of them, the unassigned ones, or one
project's.

A scope is built at the edge (a route, the chat pipeline) after the project's ownership has been
checked, and passed down as a value. The search SQL takes its condition from here, built only from
fixed strings: a project id is always a bound parameter, never text.
"""
from dataclasses import dataclass
from typing import Any, Dict, Literal

ScopeKind = Literal["all", "unassigned", "project"]


@dataclass(frozen=True)
class DocumentScope:
    kind: ScopeKind
    project_id: int | None = None

    def __post_init__(self) -> None:
        if (self.kind == "project") != (self.project_id is not None):
            raise ValueError(f"A {self.kind!r} scope {'needs' if self.kind == 'project' else 'takes no'} project_id")

    @classmethod
    def all(cls) -> "DocumentScope":
        """Every document of the user: the retrieval eval, POST /search, concept maps (until Day 20)."""
        return cls("all")

    @classmethod
    def unassigned(cls) -> "DocumentScope":
        """A chat outside any project (Decision 1A): documents with no project."""
        return cls("unassigned")

    @classmethod
    def project(cls, project_id: int) -> "DocumentScope":
        return cls("project", project_id)

    @classmethod
    def for_chat(cls, project_id: int | None) -> "DocumentScope":
        """A chat session's scope from its project_id column."""
        return cls.unassigned() if project_id is None else cls.project(project_id)

    @property
    def cache_key(self) -> str:
        """Part of every cache key whose value depends on the scope (L1, semantic cache)."""
        return f"p:{self.project_id}" if self.kind == "project" else self.kind

    def sql_condition(self, documents_alias: str) -> str:
        """A WHERE fragment on the documents table; pair it with ``sql_params``."""
        if self.kind == "all":
            return "TRUE"
        if self.kind == "unassigned":
            return f"{documents_alias}.project_id IS NULL"
        return f"{documents_alias}.project_id = :scope_project_id"

    def sql_params(self) -> Dict[str, Any]:
        return {"scope_project_id": self.project_id} if self.kind == "project" else {}
