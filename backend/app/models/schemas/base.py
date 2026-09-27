"""Shared base schemas for cross-domain DTOs and common field patterns."""

from pydantic import BaseModel


class ScopedRequest(BaseModel):
    """Base for requests that target a specific project/thread context."""

    project_id: int | None = None
    thread_id: str | None = None
