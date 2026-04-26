"""
Macro Execution Event Package
=============================

Public exports for macro execution event types and schemas.
"""

from .schemas import MacroEvent, MacroExecutionFailedEvent
from .types import MacroEventType

__all__ = [
    "MacroEvent",
    "MacroEventType",
    "MacroExecutionFailedEvent",
]
