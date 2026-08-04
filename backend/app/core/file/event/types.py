"""
File System Event Types
=======================

Event type constants for file system monitoring and changes.
"""

from enum import Enum


class FileSystemEventType(str, Enum):
    """
    File System event types.

    Events related to file system monitoring and changes.
    """

    FILE_CREATED = "fs.file_created"
    FILE_MODIFIED = "fs.file_modified"
    FILE_DELETED = "fs.file_deleted"
    FILE_MOVED = "fs.file_moved"
    DIRECTORY_CREATED = "fs.dir_created"
    DIRECTORY_DELETED = "fs.dir_deleted"
    WATCHER_STARTED = "fs.watcher_started"
    WATCHER_STOPPED = "fs.watcher_stopped"
