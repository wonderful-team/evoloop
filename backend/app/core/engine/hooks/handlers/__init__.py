"""
Built-in hook handlers for EvoLoop lifecycle events.

These handlers are registered with the global hook_system during module load.
"""

from app.core.engine.hooks.handlers.compaction import pre_compact_save_state
from app.core.engine.hooks.handlers.error import error_handler
from app.core.engine.hooks.handlers.notifications import notification_handler
from app.core.engine.hooks.handlers.quality import stop_quality_gate
from app.core.engine.hooks.handlers.subagents import (
    subagent_start_handler,
    subagent_stop_handler,
)
from app.core.engine.hooks.handlers.tools import (
    post_tool_use_failure_logging,
    post_tool_use_logging,
)
from app.core.engine.hooks.handlers.user import user_prompt_submit_handler

__all__ = [
    "pre_compact_save_state",
    "post_tool_use_logging",
    "post_tool_use_failure_logging",
    "stop_quality_gate",
    "notification_handler",
    "subagent_start_handler",
    "subagent_stop_handler",
    "user_prompt_submit_handler",
    "error_handler",
]
