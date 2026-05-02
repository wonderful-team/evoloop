"""
Core file operations module.

Provides domain-agnostic file I/O operations and models.
This is the foundational layer for all file-related functionality.

Migration Note:
    This module is the new home for file operations previously in app.utils.file.
    During migration, both locations are maintained for backward compatibility.
"""

# Editor (for advanced use)
from . import editor
# Directory Operations
from .directory import (
    DirectoryEntry,
    DirectoryInfo,
    DirectoryOperationResult,
    DirectoryStatus,
    # Directory operations
    create_directory,
    delete_directory,
    delete_file,
    # Utility
    ensure_directory,
    # Tree generation
    generate_tree,
    # Directory info
    get_directory_info,
    get_directory_size,
    is_empty_directory,
    # Directory listing
    list_directory,
    move_path,
)
# I/O Operations
from .io import (
    DEFAULT_PAGE_SIZE,
    # Constants
    LARGE_FILE_THRESHOLD,
    append_to_file,
    compute_file_hash,
    detect_encoding,
    ensure_dir,
    # Utility functions
    file_exists,
    # File info
    get_file_info,
    get_pagination_info,
    # Read operations
    read_file,
    read_lines_streaming,
    # Write operations
    write_file,
)
# Models
from .models import (
    FileInfo,
    FileMetadata,
    FileStatus,
    ReadResult,
    WriteResult,
)
# Outline extraction (file structure analysis)
from .outline import (
    OutlineEntry,
    get_file_outline,
    get_large_file_preview,
)
from .schemas import (
    FileChunk,
    PaginationInfo,
)
# Legacy service (kept for backward compatibility)
from .service import (
    filter_code_files,
    is_binary_file,
    is_test_file,
    is_text_file,
    resolve_path,
    walk_tree,
)
# Verification utilities (safe read/write with hash)
from .verification import (
    apply_edit_with_verification,
    get_file_stats,
    safe_read_with_hash,
    verify_file_hash,
    write_file_with_verification,
)
# File watching (event system integrated)
from .watcher import (
    FileWatcher,
    FileWatcherManager,
)

__all__ = [
    # Models
    "FileInfo",
    "FileStatus",
    "ReadResult",
    "WriteResult",
    "FileChunk",
    "PaginationInfo",
    "FileMetadata",

    # I/O Operations
    "read_file",
    "read_lines_streaming",
    "write_file",
    "append_to_file",

    # File Info
    "get_file_info",
    "detect_encoding",
    "compute_file_hash",
    "get_pagination_info",

    # File Utility
    "file_exists",
    "ensure_dir",

    # Directory Operations
    "list_directory",
    "DirectoryEntry",
    "create_directory",
    "delete_directory",
    "delete_file",
    "move_path",
    "DirectoryOperationResult",
    "DirectoryStatus",
    "get_directory_info",
    "get_directory_size",
    "DirectoryInfo",
    "generate_tree",
    "ensure_directory",
    "is_empty_directory",

    # Editor
    "editor",

    # Verification
    "safe_read_with_hash",
    "verify_file_hash",
    "write_file_with_verification",
    "apply_edit_with_verification",
    "get_file_stats",

    # Outline
    "get_file_outline",
    "get_large_file_preview",
    "OutlineEntry",

    # Watcher (event system)
    "FileWatcher",
    "FileWatcherManager",
    "FileWatcherEvent",

    # Constants
    "LARGE_FILE_THRESHOLD",
    "DEFAULT_PAGE_SIZE",

    # Legacy service
    "walk_tree",
    "resolve_path",
    "is_binary_file",
    "is_text_file",
    "is_test_file",
    "filter_code_files",
]
