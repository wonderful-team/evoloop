from app.core.atlas.source import persistence
from app.core.context import ContextManager
from app.core.tools import evoloop_tool
from app.utils.controller_response import ControllerResponse


@evoloop_tool(summary_template="evoloop.tool_summary.list_app_maps")
async def list_app_maps(project_id: int | None = None) -> str:
    """List all active AppMaps of the current project."""
    pid = project_id or ContextManager.resolve_project_id(
        allow_global=False, request_temp=True
    )
    if not pid:
        return ControllerResponse.error("No project_id available.")
    maps = await persistence.list_app_maps(pid)
    if not maps:
        return ControllerResponse.success(f"No AppMaps found for project {pid}.")
    lines = [f"AppMaps for project {pid} (count: {len(maps)}):"]
    for m in maps:
        lines.append(
            f"- #{m.id} {m.entity} v{m.map_version} [{m.platform}] actions={len(m.actions)} routes={len(m.routes)}"
        )
    return ControllerResponse.success("\n".join(lines))
