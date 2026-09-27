"""Atlas source event schemas."""

from typing import Any

from app.core.atlas.source.event.types import AppMapEventType
from app.core.events.base import BaseEvent


class AppMapEvent(BaseEvent):
    """Published when an AppMap is created or superseded."""

    source: str = "atlas.source"

    app_map_id: int = 0
    project_id: int = 0
    entity: str = ""
    map_version: int = 1
    content_hash: str = ""
    superseded_by: int | None = None
    action: str = "created"

    # No frontend consumer currently listens for app_map events. Keep the schema
    # but do not bridge to SSE until a UI component actually subscribes.
    is_public: bool = False
    broadcast_channel: str = "system"

    def model_post_init(self, __context: Any) -> None:
        if self.action == "superseded":
            self.event_type = AppMapEventType.SUPERSEDED.value
        else:
            self.event_type = AppMapEventType.CREATED.value
        self.data = {
            "app_map_id": self.app_map_id,
            "project_id": self.project_id,
            "entity": self.entity,
            "map_version": self.map_version,
            "content_hash": self.content_hash,
            "superseded_by": self.superseded_by,
            "action": self.action,
        }
