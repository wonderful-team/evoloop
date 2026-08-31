"""AppMap persistence: save / version management / event publishing."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select

from app.core.atlas.source.event import (
    publish_app_map_created,
    publish_app_map_superseded,
)
from app.core.file import compute_sha256
from app.infrastructure.database import session_scope
from app.models.app_map import AppMap
from app.models.codebase import AppMapRouteLink, CodeChunk, Repository, SourceFile

logger = logging.getLogger(__name__)


def compute_content_hash(payload: dict) -> str:
    stable = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return compute_sha256(stable)[:32]


async def _create_app_map_route_links(
    db,
    app_map_id: int,
    project_id: int,
    routes: list[dict],
    actions: list[dict],
    db_tables: list[dict],
) -> None:
    """Link an AppMap's routes/actions/tables to backing CodeChunk rows.

    Matching is best-effort: when a unique CodeChunk cannot be identified the
    link is still created with ``code_chunk_id=None`` and ``is_verified=False``
    so that consumers can surface unresolved entries.
    """
    stmt = (
        select(CodeChunk, SourceFile.path)
        .join(SourceFile, CodeChunk.source_file_id == SourceFile.id)
        .join(Repository, SourceFile.repository_id == Repository.id)
        .where(Repository.project_id == project_id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    api_routes: dict[tuple[str, str], list[tuple[int, str]]] = {}
    db_models: dict[str, list[int]] = {}
    identifier_index: dict[str, list[tuple[int, str]]] = {}

    for chunk, file_path in rows:
        if chunk.is_api_route and chunk.api_method and chunk.api_path:
            key = (chunk.api_method.upper(), chunk.api_path)
            api_routes.setdefault(key, []).append((chunk.id, file_path))
        if chunk.is_db_model and chunk.db_table_name:
            db_models.setdefault(chunk.db_table_name.lower(), []).append(chunk.id)
        name = chunk.identifier.lower()
        identifier_index.setdefault(name, []).append((chunk.id, file_path))
        if "." in name:
            short = name.rsplit(".", 1)[1]
            identifier_index.setdefault(short, []).append((chunk.id, file_path))

    links: list[AppMapRouteLink] = []

    for route in routes or []:
        method = (route.get("method") or "GET").upper()
        url = route.get("url", "")
        key = (method, url)
        matches = api_routes.get(key, [])
        chunk_id = matches[0][0] if matches else None
        links.append(
            AppMapRouteLink(
                app_map_id=app_map_id,
                code_chunk_id=chunk_id,
                relation_kind="route",
                logical_path=url,
                logical_method=method,
                is_verified=chunk_id is not None,
            )
        )

    for table in db_tables or []:
        table_name = table.get("table", "")
        matches = db_models.get(table_name.lower(), [])
        chunk_id = matches[0] if matches else None
        links.append(
            AppMapRouteLink(
                app_map_id=app_map_id,
                code_chunk_id=chunk_id,
                relation_kind="db_table",
                logical_path=table_name,
                logical_method=None,
                is_verified=chunk_id is not None,
            )
        )

    for action in actions or []:
        action_name = (action.get("name") or "").lower()
        controller = action.get("controller") or ""
        chunk_id = None
        if action_name and action_name in identifier_index:
            chunk_id = identifier_index[action_name][0][0]
        elif controller:
            controller_lower = controller.lower()
            for chunk, file_path in rows:
                if (
                    controller_lower in file_path.lower()
                    and action_name in chunk.identifier.lower()
                ):
                    chunk_id = chunk.id
                    break
        links.append(
            AppMapRouteLink(
                app_map_id=app_map_id,
                code_chunk_id=chunk_id,
                relation_kind="action",
                logical_path=controller or None,
                logical_method=None,
                is_verified=chunk_id is not None,
            )
        )

    if links:
        db.add_all(links)


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
    content_hash = compute_content_hash({
        "routes": routes,
        "actions": actions,
        "elements": elements,
        "db_tables": db_tables,
        "extra": extra or {},
    })

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

        await _create_app_map_route_links(
            db, new_id, project_id, routes, actions, db_tables
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
