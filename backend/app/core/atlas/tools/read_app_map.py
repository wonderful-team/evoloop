from app.core.atlas.source import persistence
from app.core.context import ContextManager
from app.core.tools import evoloop_tool
from app.utils.controller_response import ControllerResponse
from app.utils.yaml import safe_yaml_dumps


@evoloop_tool(summary_template="evoloop.tool_summary.read_app_map")
async def read_app_map(entity: str, project_id: int | None = None) -> str:
    """Read the active AppMap for an entity (used for incremental updates)."""
    pid = project_id or ContextManager.resolve_project_id(
        allow_global=False, request_temp=True
    )
    if not pid:
        return ControllerResponse.error("No project_id available.")
    app_map = await persistence.get_active_app_map(pid, entity)
    if app_map is None:
        return ControllerResponse.not_found(
            f"entity='{entity}' in project {pid}", item_type="app_map"
        )
    return ControllerResponse.success(
        f"AppMap '{entity}' v{app_map.map_version} (id={app_map.id})",
        details=safe_yaml_dumps(
            {
                "entity": app_map.entity,
                "platform": app_map.platform,
                "aliases": app_map.aliases,
                "routes": app_map.routes,
                "actions": app_map.actions,
                "elements": app_map.elements,
                "db_tables": app_map.db_tables,
                "map_version": app_map.map_version,
                "content_hash": app_map.content_hash,
            }
        ),
    )
