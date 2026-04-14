from typing import Any

from pydantic import BaseModel, Field


class Document(BaseModel):
    """Universal document model shared across indexing and embedding pipelines."""

    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None
    embedding: list[float] | None = None
