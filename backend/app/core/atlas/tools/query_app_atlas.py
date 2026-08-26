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
):
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
        logger.exception(f"[AtlasTool] Failed to retrieve context for {bundle_ids}: {e}")
        return f"Error: Unable to retrieve atlas for {bundle_ids}. Details: {str(e)}", {"status": "error"}
