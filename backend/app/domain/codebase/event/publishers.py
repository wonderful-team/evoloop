"""
Codebase Indexing Event Publishers
===================================

Helper functions for publishing codebase indexing events.
"""

from app.core.events import system_bus

from .schemas import (
    FileModifiedEvent,
    FileMovedEvent,
    FileRemovedEvent,
    GenerationStatusChangedEvent,
    IndexingCompletedEvent,
    IndexingStatusChangedEvent,
)


async def publish_file_modified(repo_id: int, file_path: str) -> None:
    """Publish a file modified event."""
    await system_bus.publish(FileModifiedEvent(repo_id=repo_id, file_path=file_path))


async def publish_file_removed(repo_id: int, file_path: str) -> None:
    """Publish a file removed event."""
    await system_bus.publish(FileRemovedEvent(repo_id=repo_id, file_path=file_path))


async def publish_file_moved(repo_id: int, src_path: str, dest_path: str) -> None:
    """Publish a file moved event."""
    await system_bus.publish(FileMovedEvent(repo_id=repo_id, src_path=src_path, dest_path=dest_path))


async def publish_indexing_status_changed(project_id: int, status: str, repo_id: int | None = None) -> None:
    """Publish a public indexing status change event (bridged to frontend SSE)."""
    await system_bus.publish(
        IndexingStatusChangedEvent(
            project_id=project_id,
            repo_id=repo_id,
            status=status,
        )
    )


async def publish_indexing_completed(project_id: int, repo_id: int) -> None:
    """Publish an indexing completed event (triggers downstream generation)."""
    await system_bus.publish(
        IndexingCompletedEvent(
            project_id=project_id,
            repo_id=repo_id,
        )
    )


async def publish_generation_status_changed(
    project_id: int,
    item: str,
    status: str,
    error: str | None = None,
) -> None:
    """Publish a generation artifact status change event."""
    await system_bus.publish(
        GenerationStatusChangedEvent(
            project_id=project_id,
            item=item,
            status=status,
            error=error,
        )
    )
