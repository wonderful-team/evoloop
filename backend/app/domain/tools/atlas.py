import logging

from app.core.atlas import atlas_engine
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_pollable=True,
    is_hidden=True,
    summary_template="database_logger.tool_summary.query_app_atlas"
)
async def query_app_atlas(bundle_ids: str | list[str]) -> str:
    """
    Retrieves structural UI maps (Atlas) for one or more applications from the graph database.
    
    Use this when you are unfamiliar with multiple apps' UIs, need to find paths between apps,
    or want to understand the UI landscape for a cross-application task.
    
    Args:
        bundle_ids: A single bundle ID or a list of bundle IDs (e.g., ['com.apple.Safari', 'com.navicat.NavicatPremium']).
        
    Returns:
        A combined structured markdown summary of the requested applications' UI atlases.
    """
    try:
        return await atlas_engine.query_app_atlas(bundle_ids)
    except Exception as e:
        logger.error(f"[AtlasTool] Failed to retrieve context for {bundle_ids}: {e}")
        return f"Error: Unable to retrieve atlas for {bundle_ids}. Details: {str(e)}"


@evoloop_tool(
    is_pollable=True,
    is_hidden=True,
    summary_template="database_logger.tool_summary.list_app_atlas"
)
async def list_app_atlas() -> str:
    """
    Lists all applications that have structural UI maps (Atlas) available in the graph database.
    
    Use this to discover which apps you have 'experience' with and can query using query_app_atlas.
    Atlas data is built automatically as the Agent performs tasks.
    """
    try:
        return await atlas_engine.list_apps()
    except Exception as e:
        logger.error(f"[AtlasTool] Failed to list apps: {e}")
        return f"Error: Unable to list apps in Atlas. Details: {str(e)}"
