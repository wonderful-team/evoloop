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

    # Bridged to frontend: users see "新地图已保存" notifications.
    is_public: bool = True
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


class AppMapGenerateCompletedEvent(BaseEvent):
    """Published when an AppMap is ready for downstream macro synthesis.

    Emitted after the Agent explicitly confirms the surveyed AppMap is complete
    (via generate_macros_from_app_map) or when the AppMap generation workflow is
    otherwise finished. The macro module subscribes to this event and schedules
    synthesis independently.
    """

    source: str = "atlas.source"
    event_type: str = AppMapEventType.GENERATE_COMPLETED.value

    app_map_id: int = 0
    project_id: int = 0
    member_id: int = 0

    # Internal command event: not surfaced to the frontend as a notification.
    is_public: bool = False
    broadcast_channel: str = "none"

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "app_map_id": self.app_map_id,
            "project_id": self.project_id,
            "member_id": self.member_id,
        }
