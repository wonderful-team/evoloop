"""
Embedding Event Schemas
=======================

Pydantic data classes for embedding infrastructure events.
"""

from typing import Any

from app.core.events.base import BaseEvent
from app.core.events.registry import SystemEventType


class EmbeddingUpdatedEvent(BaseEvent):
    """Event published when embeddings are updated for a project."""

    event_type: str = SystemEventType.EMBEDDING_UPDATED
    repo_id: int = 0
    project_id: int = 0

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "repo_id": self.repo_id,
            "project_id": self.project_id,
        }
