"""
Core file operations module.

Provides domain-agnostic file I/O operations and models.
This is the foundational layer for all file-related functionality.

Migration Note:
    This module is the new home for file operations previously in app.utils.file.
    During migration, both locations are maintained for backward compatibility.
"""

# Editor (for advanced use)
from app.utils.filename import sanitize_filename

# Hashing Utilities
from app.utils.hash import (
    compute_content_hash,
    compute_file_hash,
    compute_hash,
    compute_md5,
    compute_sha256,
    compute_state_id,
    compute_version_hash,
    sha256_digest,
)
from app.utils.path import (
    cleanup_file,
    get_absolute_path,
    get_relative_path,
    get_unique_filename,
    is_path_readable,
    is_path_writable,
    is_safe_path,
    normalize_path,
    safe_join,
)

from . import editor
from .constants import DEFAULT_PAGE_SIZE, LARGE_FILE_THRESHOLD

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
from .filter import (
    get_grep_exclude_args,
    get_ripgrep_exclude_args,
    is_encrypted_path,
    is_ignored_path,
)

# I/O Operations
from .io import (
    append_to_file,
    detect_encoding,
    ensure_dir,
    # Utility functions
    file_exists,
    # File info
    get_file_info,
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
from .searcher import FileSearcher

# Legacy service (kept for backward compatibility)
from .service import (
    ensure_local_path,
    filter_code_files,
    resolve_path,
    walk_tree,
)
from .traverser import FileTraverser, TraverseOptions
from .tree import TreeService
from .types import (
    get_category as get_file_category,
)
from .types import (
    get_extension as get_file_ext,
)
from .types import (
    guess_mime as guess_mime_type,
)
from .types import (
    is_archive as is_archive_file,
)
from .types import (
    is_audio as is_audio_file,
)
from .types import (
    is_binary as is_binary_file,
)
from .types import (
    is_code as is_code_file,
)
from .types import (
    is_document as is_document_file,
)
from .types import (
    is_image as is_image_file,
)
from .types import (
    is_test as is_test_file,
)
from .types import (
    is_text as is_text_file,
)
from .types import (
    is_video as is_video_file,
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

# No more service level cleanup_file

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
    "detect_encoding",
    "get_file_info",
    # Hashing Operations
    "compute_md5",
    "compute_sha256",
    "compute_hash",
    "compute_file_hash",
    "compute_version_hash",
    "compute_state_id",
    "compute_content_hash",
    "sha256_digest",
    # File Utility
    "file_exists",
    "ensure_dir",
    "cleanup_file",
    # Path Utilities
    "safe_join",
    "is_safe_path",
    "normalize_path",
    "sanitize_filename",
    "get_unique_filename",
    "get_relative_path",
    "get_absolute_path",
    "is_path_readable",
    "is_path_writable",
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
    # Constants
    "LARGE_FILE_THRESHOLD",
    "DEFAULT_PAGE_SIZE",
    # Legacy service
    "walk_tree",
    "resolve_path",
    "ensure_local_path",
    "get_file_ext",
    "guess_mime_type",
    "get_file_category",
    "is_archive_file",
    "is_audio_file",
    "is_binary_file",
    "is_code_file",
    "is_document_file",
    "is_image_file",
    "is_test_file",
    "is_text_file",
    "is_video_file",
    "filter_code_files",
    # Unified File Center (NEW)
    "FileTraverser",
    "TraverseOptions",
    "TreeService",
    "FileSearcher",
    # Filtering (NEW)
    "is_ignored_path",
    "is_encrypted_path",
    "get_grep_exclude_args",
    "get_ripgrep_exclude_args",
]
