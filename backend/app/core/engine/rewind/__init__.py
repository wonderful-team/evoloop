"""
Rewind Module
=============

Core framework for conversation rewinding and retry operations.

This module provides the orchestrator, event type constants, data models,
and exceptions. Domain-specific cleanup event classes live in their
respective modules' event/schemas.py (e.g. FilesCleanupEvent in app.core.file.event.schemas).
"""
from app.core.engine.rewind.exceptions import PartialRewindError, RewindError
from app.core.engine.rewind.models import RewindOperation as RewindRequest, RewindResult
from app.core.engine.rewind.orchestrator import RewindOrchestrator

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
