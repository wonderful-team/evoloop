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
    # Directory listing
    list_directory,
    DirectoryEntry,

    # Directory operations
    create_directory,
    delete_directory,
    delete_file,
    move_path,
    DirectoryOperationResult,
    DirectoryStatus,

    # Directory info
    get_directory_info,
    get_directory_size,
    DirectoryInfo,

    # Tree generation
    generate_tree,

    # Utility
    ensure_directory,
    is_empty_directory,
)
# I/O Operations
from .io import (
    # Read operations
    read_file,
    read_lines_streaming,

    # Write operations
    write_file,
    append_to_file,

    # File info
    get_file_info,
    detect_encoding,
    compute_file_hash,
    get_pagination_info,

    # Utility functions
    file_exists,
    ensure_dir,

    # Constants
    LARGE_FILE_THRESHOLD,
    DEFAULT_PAGE_SIZE,
)
# Models
from .models import (
    FileInfo,
    FileStatus,
    ReadResult,
    WriteResult,
    FileChunk,
    PaginationInfo,
    FileMetadata,
)
# Outline extraction (file structure analysis)
from .outline import (
    get_file_outline,
    get_large_file_preview,
    OutlineEntry,
)
# Legacy service (kept for backward compatibility)
from .service import (
    walk_tree,
    resolve_path,
    is_binary_file,
    is_text_file,
    is_test_file,
    filter_code_files,
)
# Verification utilities (safe read/write with hash)
from .verification import (
    safe_read_with_hash,
    verify_file_hash,
    write_file_with_verification,
    apply_edit_with_verification,
    get_file_stats,
)
# File watching (event system integrated)
from .watcher import (
    FileWatcher,
    FileWatcherManager,
    FileWatcherEvent,
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
