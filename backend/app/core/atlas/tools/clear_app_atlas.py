import logging

from app.core.atlas import atlas_engine
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(summary_template="evoloop.tool_summary.clear_app_atlas")
async def clear_app_atlas():
    """
    Permanently deletes all historical Atlas data (UI maps) from the memory store.

    Use this only when you want to reset the agent's spatial memory, for example
    if the UI layouts have significantly changed after a major system update.
    """
    try:
        await atlas_engine.clear_atlas()
        return "Successfully cleared all historical Atlas data.", {"status": "success"}
    except Exception as e:
        logger.exception(f"[AtlasTool] Failed to clear Atlas: {e}")
        return f"Error: Unable to clear Atlas data. Details: {str(e)}", {"status": "error"}
