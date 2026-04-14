"""
Rewind Module
=============

Event-driven architecture for conversation rewinding and retry operations.

This module provides a centralized rewind orchestrator that coordinates
cleanup operations across different domains through event-driven handlers.

Usage:
    from app.core.checkpoint.rewind import RewindOrchestrator, RewindResult
    
    orchestrator = RewindOrchestrator(event_bus=system_bus)
    result = await orchestrator.perform_rewind(
        thread_id="thread-123",
        target_message_id="msg-456",
        revert_files=True
    )
"""
from app.api.routes.conversations import RewindRequest
from app.core.checkpoint.rewind.checkpoint_handler import CheckpointRewind
from app.core.checkpoint.rewind.exceptions import PartialRewindError, RewindError
from app.core.checkpoint.rewind.handlers import MessageRewind

__all__ = [
    # Main orchestrator
    "RewindOrchestrator",
    # Handlers
    "MessageRewind",
    "CheckpointRewind",
    # Data models
    "RewindRequest",
    "RewindResult",
    # Exceptions
    "RewindError",
    "PartialRewindError",
]

from app.core.checkpoint.rewind.models import RewindResult
from app.core.checkpoint.rewind.orchestrator import RewindOrchestrator
