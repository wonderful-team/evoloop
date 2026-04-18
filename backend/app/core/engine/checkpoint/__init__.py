"""Checkpoint management for file snapshots and rollback."""

from .manager import CheckpointManager, checkpoint_manager

__all__ = ["CheckpointManager", "checkpoint_manager"]
