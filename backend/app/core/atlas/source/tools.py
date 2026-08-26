"""Agent tools for AppMap generation (write / read / list)."""

from __future__ import annotations

import logging
from typing import Annotated

from app.core.atlas.source import persistence
from app.core.atlas.source.schemas import AppMapPayload
from app.core.atlas.source.validate import validate_app_map
from app.core.context.manager import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool, get_working_directory
from app.core.tools.base import InjectedToolArg
from app.utils.controller_response import ControllerResponse
from app.utils.yaml import safe_yaml_dumps

logger = logging.getLogger(__name__)


def _resolve_project_id() -> int | None:
    return ContextManager.resolve_project_id(allow_global=False, request_temp=True)


@evoloop_tool(is_state_mutating=True, summary_template="evoloop.tool_summary.write_app_map")
async def write_app_map(
    entity: str,
    platform: str,
    aliases: list[str],
    routes: list[dict],
    actions: list[dict],
    elements: list[dict],
    db_tables: list[dict],
    extra: dict | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """Save the surveyed AppMap for one entity.

    `extra` carries site-level facts discovered during survey, notably
    {"base_url": "http://host:port"} when the admin site's origin is known
    from project config — templates emit full URLs when present.
    """
    project_id = _resolve_project_id()
    if not project_id:
        return ControllerResponse.error("No active project resolved for AppMap.")

    payload = AppMapPayload(
        entity=entity,
        platform=platform or "web",
        aliases=aliases or [],
        routes=routes or [],
        actions=actions or [],
        elements=elements or [],
        db_tables=db_tables or [],
        extra=extra or {},
    )

    project_path = get_working_directory(config)
    problems = await validate_app_map(
        payload,
        project_path=project_path or None,
        project_id=project_id,
    )
    if problems:
        return ControllerResponse.error(
            "AppMap validation failed; map NOT saved.",
            details="\n".join(f"- {p}" for p in problems),
            note="Fix the listed entries (hallucinated entries must be removed) and retry.",
        )

    thread_id = ContextManager.current().thread_id if ContextManager.current() else None
    app_map_id, map_version, created = await persistence.save_app_map(
        project_id=project_id,
        entity=entity,
        platform=payload.platform,
        aliases=payload.aliases,
        routes=[r.model_dump() for r in payload.routes],
        actions=[a.model_dump() for a in payload.actions],
        elements=[e.model_dump() for e in payload.elements],
        db_tables=[t.model_dump() for t in payload.db_tables],
        extra=payload.extra,
        generation_thread_id=thread_id,
        member_id=ContextManager.current().member_id if ContextManager.current() else 0,
    )

    if not created:
        return ControllerResponse.success(
            f"AppMap for '{entity}' unchanged (v{map_version}, id={app_map_id}).",
            note="Content hash matches the active map; no new version created.",
        )
    return ControllerResponse.success(
        f"AppMap for '{entity}' saved as v{map_version} (id={app_map_id}).",
        note="Survey complete; the map is now active.",
    )


@evoloop_tool(summary_template="evoloop.tool_summary.read_app_map")
async def read_app_map(entity: str, project_id: int | None = None) -> str:
    """Read the active AppMap for an entity (used for incremental updates)."""
    pid = project_id or _resolve_project_id()
    if not pid:
        return ControllerResponse.error("No project_id available.")
    app_map = await persistence.get_active_app_map(pid, entity)
    if app_map is None:
        return ControllerResponse.not_found(f"entity='{entity}' in project {pid}", item_type="app_map")
    return ControllerResponse.success(
        f"AppMap '{entity}' v{app_map.map_version} (id={app_map.id})",
        details=safe_yaml_dumps({
            "entity": app_map.entity,
            "platform": app_map.platform,
            "aliases": app_map.aliases,
            "routes": app_map.routes,
            "actions": app_map.actions,
            "elements": app_map.elements,
            "db_tables": app_map.db_tables,
            "map_version": app_map.map_version,
            "content_hash": app_map.content_hash,
        }),
    )


@evoloop_tool(summary_template="evoloop.tool_summary.list_app_maps")
async def list_app_maps(project_id: int | None = None) -> str:
    """List all active AppMaps of the current project."""
    pid = project_id or _resolve_project_id()
    if not pid:
        return ControllerResponse.error("No project_id available.")
    maps = await persistence.list_app_maps(pid)
    if not maps:
        return ControllerResponse.success(f"No AppMaps found for project {pid}.")
    lines = [f"AppMaps for project {pid} (count: {len(maps)}):"]
    for m in maps:
        lines.append(
            f"- #{m.id} {m.entity} v{m.map_version} [{m.platform}] "
            f"actions={len(m.actions)} routes={len(m.routes)}"
        )
    return ControllerResponse.success(
        "\n".join(lines)
    )
