"""
Codebase Indexing Event Publishers
===================================

Helper functions for publishing codebase indexing events.
"""

from app.core.events import system_bus

from .schemas import FileModifiedEvent, FileMovedEvent, FileRemovedEvent


async def publish_file_modified(repo_id: int, file_path: str) -> None:
    """Publish a file modified event."""
    await system_bus.publish(FileModifiedEvent(repo_id=repo_id, file_path=file_path))


async def publish_file_removed(repo_id: int, file_path: str) -> None:
    """Publish a file removed event."""
    await system_bus.publish(FileRemovedEvent(repo_id=repo_id, file_path=file_path))


async def publish_file_moved(repo_id: int, src_path: str, dest_path: str) -> None:
    """Publish a file moved event."""
    await system_bus.publish(FileMovedEvent(repo_id=repo_id, src_path=src_path, dest_path=dest_path))
