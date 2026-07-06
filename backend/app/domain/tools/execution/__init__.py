"""Command execution and background task tools for the Agent."""

from app.domain.tools.execution._utils import (
    MAX_OUTPUT_LINES,
    format_command_result,
    get_thread_id,
)

# Backward compatibility aliases
_get_thread_id = get_thread_id
from app.domain.tools.execution.background import (
    execute_in_background,
    execute_smart,
    run_command_background,
)
from app.domain.tools.execution.execute import _execute_command, execute_command
from app.domain.tools.execution.macro import run_macro
from app.domain.tools.execution.query import cancel_command, query_command_status
from app.domain.tools.execution.security import is_dangerous_command

__all__ = [
    "execute_command",
    "query_command_status",
    "cancel_command",
    "run_macro",
    "_execute_command",
    "is_dangerous_command",
    "format_command_result",
    "get_thread_id",
    "execute_in_background",
    "execute_smart",
    "run_command_background",
    "MAX_OUTPUT_LINES",
]
