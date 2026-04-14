"""Shared base schemas for cross-domain DTOs and common field patterns."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class NamedEntity(BaseModel):
    """Base for entities with id, name, and description."""

    id: str
    name: str
    description: str = ""


class TimestampedEntity(BaseModel):
    """Base for entities with created_at and updated_at."""

    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


class ProgressTrackable(BaseModel):
    """Base for task/step/execution models that track status and progress."""

    status: str
    progress: int = 0
    result: str | None = None


class SearchResponse(BaseModel):
    """Base for search result envelopes."""

    query: str
    results: list[Any]
    total: int


class ScopedRequest(BaseModel):
    """Base for requests that target a specific project/thread context."""

    project_id: int | None = None
    thread_id: str | None = None
