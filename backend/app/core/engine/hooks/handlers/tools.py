"""
Tool-use logging hook handlers.
"""

import logging

from app.core.engine.hooks.core import HookContext, HookResult

logger = logging.getLogger(__name__)


async def post_tool_use_logging(context: HookContext) -> HookResult:
    """Log tool usage for analytics and memory."""
    if not context.tool_name:
        return HookResult(success=True)

    logger.debug(f"[ToolUse] {context.tool_name}: success")

    # Track tool usage for quality scoring
    # Could track which tools lead to successful outcomes

    return HookResult(success=True)


async def post_tool_use_failure_logging(context: HookContext) -> HookResult:
    """Log tool failures for debugging and improvement."""
    if not context.tool_name:
        return HookResult(success=True)

    error_str = (
        str(context.error)
        if context.error
        else context.error_message or "Unknown error"
    )
    logger.warning(f"[ToolUseFailure] {context.tool_name} failed: {error_str}")

    return HookResult(
        success=True,
        data={
            "tool_name": context.tool_name,
            "error": error_str,
            "tool_input": context.tool_input,
        },
    )
