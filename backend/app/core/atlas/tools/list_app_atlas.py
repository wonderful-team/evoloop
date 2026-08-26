import logging

from app.core.atlas import atlas_engine
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_hidden=True,
    summary_template="evoloop.tool_summary.list_app_atlas"
)
async def list_app_atlas():
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
        logger.exception(f"[AtlasTool] Failed to list apps: {e}")
        return f"Error: Unable to list apps in Atlas. Details: {str(e)}", {"status": "error"}
