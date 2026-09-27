"""
Built-in hook handlers for EvoLoop lifecycle events.

These handlers are registered with the global hook_system during module load.
"""

from app.core.engine.hooks.handlers.error import error_handler
from app.core.engine.hooks.handlers.notifications import notification_handler
from app.core.engine.hooks.handlers.quality import stop_quality_gate
from app.core.engine.hooks.handlers.tools import (
    post_tool_use_failure_logging,
    post_tool_use_logging,
)
from app.core.engine.hooks.handlers.user import user_prompt_submit_handler

__all__ = [
    "post_tool_use_logging",
    "post_tool_use_failure_logging",
    "stop_quality_gate",
    "notification_handler",
    "user_prompt_submit_handler",
    "error_handler",
]
