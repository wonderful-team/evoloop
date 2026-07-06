import asyncio
import logging

from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    is_hidden=True,
    summary_template="evoloop.tool_summary.wait_for"
)
async def wait_for(seconds: float) -> str:
    """
    Wait for a specified number of seconds.
    Useful for UI automation to wait for elements to load or animations to finish.
    
    Args:
        seconds: Number of seconds to wait (e.g., 2, 0.5).
    """
    try:
        await asyncio.sleep(seconds)
        return f"Waited for {seconds} seconds."
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Wait tool error: {e}")
        return f"Error during wait: {e}"
