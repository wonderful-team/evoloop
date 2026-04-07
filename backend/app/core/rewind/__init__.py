"""
Rewind Module
=============

Event-driven architecture for conversation rewinding and retry operations.

This module provides a centralized rewind orchestrator that coordinates
cleanup operations across different domains through event-driven handlers.

Usage:
    from app.core.rewind import RewindOrchestrator, RewindResult
    
    orchestrator = RewindOrchestrator(event_bus=system_bus)
    result = await orchestrator.perform_rewind(
        thread_id="thread-123",
        target_message_id="msg-456",
        revert_files=True
    )
"""

from app.core.rewind.models import RewindRequest, RewindResult
from app.core.rewind.orchestrator import RewindOrchestrator
from app.core.rewind.exceptions import RewindError, PartialRewindError

__all__ = [
    # Main orchestrator
    "RewindOrchestrator",
    # Data models
    "RewindRequest",
    "RewindResult",
    # Exceptions
    "RewindError",
    "PartialRewindError",
]
