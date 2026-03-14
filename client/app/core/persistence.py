"""
Persistence utilities for LangGraph checkpoints.

PostgreSQL support has been moved to the server branch.
Client mode uses SQLite-based checkpointing.
"""
from typing import Any

_checkpointer: Any | None = None


def set_checkpointer(saver: Any):
    """Set the checkpoint saver (AsyncSqliteSaver)."""
    global _checkpointer
    _checkpointer = saver


def get_checkpointer() -> Any | None:
    """Get the checkpoint saver."""
    return _checkpointer


def get_sqlite_saver():
    """Get AsyncSqliteSaver class (lazy import)."""
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        return AsyncSqliteSaver
    except ImportError:
        return None
