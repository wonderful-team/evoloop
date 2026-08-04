import logging
from typing import Literal

from app.core.atlas import atlas_engine
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_hidden=True,
    summary_template="evoloop.tool_summary.query_app_atlas"
)
async def query_app_atlas(
    bundle_ids: str | list[str],
    state_id: str | None = None,
    platform: Literal["macos", "android"] = "macos",
) -> str:
    """
    Retrieves structural UI maps (Atlas) for one or more applications from the graph database.

    Use this when you are unfamiliar with multiple apps' UIs, need to find paths between apps,
    or want to understand the UI landscape for a cross-application task.

    Args:
        bundle_ids: A single bundle ID or a list of bundle IDs (e.g., ['com.apple.Safari', 'com.navicat.NavicatPremium']).
        state_id: Optional. If provided, returns detailed element list for this specific UI state/screen.
        platform: The target platform ('macos' or 'android'). Defaults to 'macos'.

    Returns:
        A combined structured markdown summary of the requested applications' UI atlases.
    """
    try:
        content = await atlas_engine.query_app_atlas(bundle_ids, state_id=state_id, platform=platform)
        # Extract count if bundle_ids is a list
        count = len(bundle_ids) if isinstance(bundle_ids, list) else 1
        return content, {"count": count, "state_id": state_id, "platform": platform}
    except Exception as e:
        logger.error(f"[AtlasTool] Failed to retrieve context for {bundle_ids}: {e}")
        return f"Error: Unable to retrieve atlas for {bundle_ids}. Details: {str(e)}", {"status": "error"}


@evoloop_tool(
    is_hidden=True,
    summary_template="evoloop.tool_summary.list_app_atlas"
)
async def list_app_atlas() -> str:
    """
    Lists all applications that have structural UI maps (Atlas) available in the graph database.

    Use this to discover which apps you have 'experience' with and can query using query_app_atlas.
    Atlas data is built automatically as the Agent performs tasks.
    """
    try:
        # Since atlas_engine.list_apps() returns a string, we'll need to
        # either change the service or parse the string.
        # Changing the service is cleaner.
        # But for now, let's just use the service and extract the count
        # from the underlying store in the tool for speed.
        apps = await atlas_engine.store.list_apps()
        content = await atlas_engine.list_apps()
        return content, {"count": len(apps)}
    except Exception as e:
        logger.error(f"[AtlasTool] Failed to list apps: {e}")
        return f"Error: Unable to list apps in Atlas. Details: {str(e)}", {"status": "error"}


@evoloop_tool(summary_template="evoloop.tool_summary.clear_app_atlas")
async def clear_app_atlas() -> str:
    """
    Permanently deletes all historical Atlas data (UI maps) from the memory store.

    Use this only when you want to reset the agent's spatial memory, for example
    if the UI layouts have significantly changed after a major system update.
    """
    try:
        await atlas_engine.clear_atlas()
        return "Successfully cleared all historical Atlas data.", {"status": "success"}
    except Exception as e:
        logger.error(f"[AtlasTool] Failed to clear Atlas: {e}")
        return f"Error: Unable to clear Atlas data. Details: {str(e)}", {"status": "error"}
