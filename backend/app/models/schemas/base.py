"""Shared base schemas for cross-domain DTOs and common field patterns."""

from datetime import datetime

from pydantic import BaseModel


class TimestampedEntity(BaseModel):
    """Base for entities with created_at and updated_at."""

    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


class ScopedRequest(BaseModel):
    """Base for requests that target a specific project/thread context."""

    project_id: int | None = None
    thread_id: str | None = None
