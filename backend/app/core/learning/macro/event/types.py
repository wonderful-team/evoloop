"""
Macro Execution Event Types
===========================

Event type constants for macro execution.
"""

from enum import Enum


class MacroEventType(str, Enum):
    """
    Macro Execution event types.
    """

    EXECUTION_FAILED = "macro.execution_failed"
