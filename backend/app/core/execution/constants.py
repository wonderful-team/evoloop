"""Execution-wide constants shared across execution subpackages."""

from __future__ import annotations

# Output formatting limits used by command execution and background tasks.
MAX_OUTPUT_LINES = 1000
MAX_TRUNCATED_STDOUT_LINES = 900
MAX_TRUNCATED_STDERR_LINES = 100

# Background task output / query limits
DEFAULT_OUTPUT_LINES = 50
MAX_OUTPUT_BUFFER_LINES = 1000

# Background task manager lifecycle limits
MAX_TASKS_PER_THREAD = 50
TASK_CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes
MAX_TASK_AGE_SECONDS = 3600 * 24  # 24 hours
DEFAULT_TASK_TIMEOUT_SECONDS = 3600  # 1 hour

# Result serialization limits
MAX_RESULT_LIST_ITEMS = 100
MAX_RESULT_STRING_LENGTH = 1000

# Command execution defaults / bounds
MAX_COMMAND_TITLE_LENGTH = 60
QUICK_TIMEOUT_SECONDS = 60
MIN_COMMAND_TIMEOUT_SECONDS = 10
MAX_COMMAND_TIMEOUT_SECONDS = 3600
