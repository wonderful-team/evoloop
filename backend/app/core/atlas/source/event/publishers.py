"""Atlas source event publishers."""

from app.core.atlas.source.event.schemas import AppMapEvent
from app.core.events import system_bus


async def publish_app_map_created(
    app_map_id: int,
    project_id: int,
    entity: str,
    map_version: int,
    content_hash: str,
    thread_id: str | None = None,
) -> None:
    await system_bus.publish(
        AppMapEvent(
            action="created",
            app_map_id=app_map_id,
            project_id=project_id,
            entity=entity,
            map_version=map_version,
            content_hash=content_hash,
            thread_id=thread_id,
        )
    )


async def publish_app_map_superseded(
    app_map_id: int,
    project_id: int,
    entity: str,
    map_version: int,
    content_hash: str,
    superseded_by: int | None = None,
) -> None:
    await system_bus.publish(
        AppMapEvent(
            action="superseded",
            app_map_id=app_map_id,
            project_id=project_id,
            entity=entity,
            map_version=map_version,
            content_hash=content_hash,
            superseded_by=superseded_by,
        )
    )
