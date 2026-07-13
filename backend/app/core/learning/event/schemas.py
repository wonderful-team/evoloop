"""
Learning Event Schemas
======================

Pydantic data classes for learning domain events.
"""

from typing import Any

from app.core.events.base import BaseEvent


class SkillMutatedEvent(BaseEvent):
    """Event published when a skill lifecycle event (created/updated/deleted) occurs."""
    skill_id: int = 0
    action: str = ""
    namespace: str | None = None
    name: str | None = None

    def model_post_init(self, __context: Any) -> None:
        from app.core.events.registry import SystemEventType
        event_type_map = {
            "create": SystemEventType.SKILL_CREATED,
            "update": SystemEventType.SKILL_UPDATED,
            "delete": SystemEventType.SKILL_DELETED,
        }
        self.event_type = event_type_map.get(self.action) or ""
        self.data = {
            "skill_id": self.skill_id,
            "action": self.action,
            "namespace": self.namespace,
            "name": self.name,
        }
