"""Atlas source event subscribers.

APP_MAP_CREATED is is_public=True, so frontend SSE notification happens through
the automatic event bridge — this subscriber only adds observability. Macro
synthesis is NOT triggered here (explicit generate_macros call only).
"""

from __future__ import annotations

import logging

from app.core.atlas.source.event.types import AppMapEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class AppMapLifecycleSubscriber:
    @event_subscribe(AppMapEventType.CREATED)
    async def on_app_map_created(self, event):
        data = event.data or {}
        logger.info(
            "[AppMap] created: project=%s entity=%s v%s (id=%s)",
            data.get("project_id"),
            data.get("entity"),
            data.get("map_version"),
            data.get("app_map_id"),
        )

    @event_subscribe(AppMapEventType.SUPERSEDED)
    async def on_app_map_superseded(self, event):
        data = event.data or {}
        logger.info(
            "[AppMap] superseded: id=%s → new=%s",
            data.get("app_map_id"),
            data.get("superseded_by"),
        )

    @event_subscribe("system.artifact_validation")
    async def on_artifact_validation(self, event):
        if event.item == "appmap":
            from sqlalchemy import select, func
            from sqlalchemy.orm import Session
            from app.infrastructure.database.resource_manager import db_resource_manager as rm
            from app.models.app_map import AppMap
            try:
                with Session(rm.sync_engine) as session:
                    count = session.scalar(
                        select(func.count(AppMap.id)).where(AppMap.project_id == event.project_id)
                    )
                    event.is_valid = bool(count and count > 0)
            except Exception:
                event.is_valid = False
