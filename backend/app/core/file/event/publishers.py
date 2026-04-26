"""
File System Event Publishers
============================

Helper functions for publishing file system events.
"""

from app.core.events import system_bus

from .schemas import FileWatcherEvent


async def publish_file_watcher_event(
    event_type: str, path: str, watch_path: str = "", **kwargs
) -> None:
    """Publish a generic file watcher event."""
    data = {"path": path, **kwargs}
    if watch_path:
        data["watch_path"] = watch_path
    await system_bus.publish(
        FileWatcherEvent(event_type=event_type, data=data)
    )


async def publish_files_cleanup(thread_id: str, file_operations: list[dict]) -> None:
    """Publish a file cleanup event for rewind operations."""
    from app.core.file.rewind import FilesCleanupEvent

    await system_bus.publish(
        FilesCleanupEvent(thread_id=thread_id, file_operations=file_operations)
    )
