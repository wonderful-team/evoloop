"""
Tool Event Types
================

Event type constants for tool background task lifecycle.
"""

from enum import Enum


class ToolEventType(str, Enum):
    """
    Tool Domain event types.

    Events related to background task state changes and output streaming.
    """
    BACKGROUND_TASK_UPDATED = "tool.background_task_updated"
    BACKGROUND_TASK_OUTPUT = "tool.background_task_output"
