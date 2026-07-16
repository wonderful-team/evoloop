"""AppMap persistence: save / version management / event publishing."""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select

from app.core.atlas.source.event import (
    publish_app_map_created,
    publish_app_map_superseded,
)
from app.infrastructure.database import session_scope
from app.models.app_map import AppMap

logger = logging.getLogger(__name__)


def compute_content_hash(payload: dict) -> str:
    stable = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:32]


async def save_app_map(
    *,
    project_id: int,
    entity: str,
    platform: str,
    aliases: list[str],
    routes: list[dict],
    actions: list[dict],
    elements: list[dict],
    db_tables: list[dict],
    extra: dict | None = None,
    generation_thread_id: str | None = None,
    member_id: int = 0,
    validation_report: dict | None = None,
) -> tuple[int, int, bool]:
    """Persist an AppMap. Returns (app_map_id, map_version, created_new_version).

    If the active map for (project, entity) has the same content_hash the
    existing row is returned unchanged (short-circuit). Otherwise the old map
    is marked superseded and a new row with map_version+1 is inserted.
    """
    content_hash = compute_content_hash(
        {
            "routes": routes,
            "actions": actions,
            "elements": elements,
            "db_tables": db_tables,
            "extra": extra or {},
        }
    )

    async with session_scope() as db:
        stmt = select(AppMap).where(
            AppMap.project_id == project_id,
            AppMap.entity == entity,
            AppMap.status == "active",
        )
        result = await db.execute(stmt)
        old = result.scalars().first()

        if old is not None and old.content_hash == content_hash:
            logger.info(
                "[AppMap] content unchanged for %s/%s — keep v%s",
                project_id,
                entity,
                old.map_version,
            )
            return old.id, old.map_version, False

        if old is not None:
            old.status = "superseded"
            db.add(old)

        app_map = AppMap(
            project_id=project_id,
            entity=entity,
            platform=platform,
            aliases=aliases,
            routes=routes,
            actions=actions,
            elements=elements,
            db_tables=db_tables,
            extra=extra or {},
            map_version=(old.map_version + 1) if old else 1,
            content_hash=content_hash,
            generation_thread_id=generation_thread_id,
            status="active",
            member_id=member_id,
            validation_report=validation_report,
        )
        db.add(app_map)
        await db.flush()
        new_id = app_map.id
        new_version = app_map.map_version
        old_snapshot = None
        if old is not None:
            old_snapshot = (
                old.id,
                old.project_id,
                old.entity,
                old.map_version,
                old.content_hash,
            )

    if old_snapshot is not None:
        old_id, old_pid, old_entity, old_ver, old_hash = old_snapshot
        await publish_app_map_superseded(
            old_id, old_pid, old_entity, old_ver, old_hash, new_id
        )
    await publish_app_map_created(
        new_id, project_id, entity, new_version, content_hash, generation_thread_id
    )
    logger.info(
        "[AppMap] saved %s/%s v%s (id=%s)", project_id, entity, new_version, new_id
    )
    return new_id, new_version, True


async def get_app_map(app_map_id: int) -> AppMap | None:
    async with session_scope() as db:
        return await db.get(AppMap, app_map_id)


async def get_active_app_map(project_id: int, entity: str) -> AppMap | None:
    async with session_scope() as db:
        stmt = select(AppMap).where(
            AppMap.project_id == project_id,
            AppMap.entity == entity,
            AppMap.status == "active",
        )
        result = await db.execute(stmt)
        return result.scalars().first()


async def list_app_maps(project_id: int, status: str | None = "active") -> list[AppMap]:
    async with session_scope() as db:
        stmt = select(AppMap).where(AppMap.project_id == project_id)
        if status:
            stmt = stmt.where(AppMap.status == status)
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def operation_map_summary(project_id: int) -> str:
    """Compact text summary of active AppMaps for Agent context injection.

    One block per entity: routes + actions (with kind/risk), so the Agent knows
    which business operations the project exposes without reading full maps.
    """
    maps = await list_app_maps(project_id, status="active")
    if not maps:
        return ""
    blocks: list[str] = []
    for m in maps:
        lines = [f"### {m.entity} (platform: {m.platform}, map v{m.map_version})"]
        for r in m.routes or []:
            lines.append(
                f"- Route: {r.get('method', 'GET')} {r.get('url', '')} ({r.get('name', '')})"
            )
        for a in m.actions or []:
            rule = f" — {a['business_rule']}" if a.get("business_rule") else ""
            lines.append(
                f"- Action: {a.get('name', '')} [{a.get('kind', '?')}/{a.get('risk_tier', 'ui')}]{rule}"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
