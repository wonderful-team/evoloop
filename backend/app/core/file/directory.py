"""
Core directory operations - Domain-agnostic directory utilities.

This module provides foundational directory operations used by the tool layer.
"""

import fnmatch
import logging
import os
import shutil
from collections.abc import Iterator
from enum import Enum
from pathlib import Path

from app.constants import DEFAULT_EXCLUDED_DIRS
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.core.file.schemas import DirectoryInfo, DirectoryOperationResult, DirectoryEntry, DirectoryStatus

logger = logging.getLogger(__name__)

# ============================================================================
# File type priority for sorting (code > config > doc > other)
# ============================================================================

_FILE_TYPE_PRIORITY = {
    ".py": 10, ".js": 10, ".ts": 10, ".jsx": 10, ".tsx": 10,
    ".php": 10, ".go": 10, ".rs": 10, ".java": 10, ".kt": 10,
    ".swift": 10, ".cpp": 10, ".c": 10, ".h": 10, ".cs": 10,
    ".rb": 10, ".scala": 10, ".r": 10,
    ".json": 20, ".yaml": 20, ".yml": 20, ".toml": 20, ".ini": 20,
    ".cfg": 20, ".conf": 20, ".env": 20,
    ".md": 30, ".rst": 30, ".txt": 30, ".doc": 30, ".docx": 30,
}


def _get_entry_priority(entry: os.DirEntry) -> tuple:
    """Return sort key for directory entries. Directories first, then by type priority, then alphabetically."""
    if entry.is_dir():
        return (0, 0, entry.name.lower())
    ext = os.path.splitext(entry.name)[1].lower()
    priority = _FILE_TYPE_PRIORITY.get(ext, 99)
    return (1, priority, entry.name.lower())


def _format_size(size: int) -> str:
    """Format file size in human-readable form."""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}K"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}M"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f}G"


def _count_entries(path: str, exclude_dirs: list[str]) -> tuple[int, int, int]:
    """Count files, subdirs, and total size in a directory."""
    file_count = 0
    subdir_count = 0
    total_size = 0
    try:
        for entry in os.scandir(path):
            if entry.name.startswith('.'):
                continue
            if entry.is_dir() and entry.name in exclude_dirs:
                continue
            if entry.is_file():
                file_count += 1
                total_size += entry.stat().st_size
            elif entry.is_dir():
                subdir_count += 1
    except OSError:
        pass
    return file_count, subdir_count, total_size


def _format_dir_stats(file_count: int, subdir_count: int) -> str:
    """Format directory stats string."""
    parts = []
    if file_count > 0:
        parts.append(f"{file_count} files")
    if subdir_count > 0:
        parts.append(f"{subdir_count} dirs")
    if parts:
        return f" [{', '.join(parts)}]"
    return " [empty]"


# ============================================================================
# Directory Listing
# ============================================================================

def list_directory(
    path: str,
    recursive: bool = False,
    max_depth: int | None = None,
    exclude_dirs: list[str] | None = None,
    filter_pattern: str | None = None,
) -> Iterator[DirectoryEntry]:
    """
    List directory entries with optional recursion and filtering.
    
    Args:
        path: Directory path
        recursive: Whether to list recursively
        max_depth: Maximum depth for recursion (None = unlimited)
        exclude_dirs: Directory names to exclude (e.g., ['node_modules', '.git'])
        filter_pattern: Glob pattern to filter entries (e.g., '*.py', 'test_*')
        
    Yields:
        DirectoryEntry objects
    """
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDED_DIRS

    if not os.path.isdir(path):
        return

    base_path = Path(path).resolve()

    if recursive:
        yield from _walk_directory(base_path, base_path, 0, max_depth, exclude_dirs, filter_pattern)
    else:
        try:
            for entry in os.scandir(base_path):
                if entry.name.startswith('.'):
                    continue
                if _filter_entry(entry, filter_pattern):
                    stat = entry.stat()
                    yield DirectoryEntry(
                        name=entry.name,
                        path=str(entry.path),
                        is_dir=entry.is_dir(),
                        size=stat.st_size if entry.is_file() else 0
                    )
        except OSError as e:
            logger.warning(f"Cannot list directory {path}: {e}")


def _filter_entry(entry: os.DirEntry, filter_pattern: str | None) -> bool:
    """Check if entry matches filter pattern. Directories always pass."""
    if filter_pattern is None:
        return True
    # Directories always pass (they may contain matching files)
    if entry.is_dir():
        return True
    return fnmatch.fnmatch(entry.name, filter_pattern)


def _walk_directory(
    base_path: Path,
    current_path: Path,
    current_depth: int,
    max_depth: int | None,
    exclude_dirs: list[str],
    filter_pattern: str | None,
) -> Iterator[DirectoryEntry]:
    """Internal recursive directory walker."""
    if max_depth is not None and current_depth > max_depth:
        return

    try:
        for entry in os.scandir(current_path):
            # Skip hidden files/dirs
            if entry.name.startswith('.'):
                continue

            # Skip excluded directories
            if entry.is_dir() and entry.name in exclude_dirs:
                continue

            # Check filter
            if not _filter_entry(entry, filter_pattern):
                continue

            stat = entry.stat()
            yield DirectoryEntry(
                name=entry.name,
                path=str(entry.path),
                is_dir=entry.is_dir(),
                size=stat.st_size if entry.is_file() else 0
            )

            # Recurse into subdirectories
            if entry.is_dir() and entry.name not in exclude_dirs:
                yield from _walk_directory(
                    base_path,
                    Path(entry.path),
                    current_depth + 1,
                    max_depth,
                    exclude_dirs,
                    filter_pattern
                )
    except OSError as e:
        logger.warning(f"Cannot access {current_path}: {e}")


# ============================================================================
# Directory Operations
# ============================================================================

def create_directory(path: str, exist_ok: bool = True) -> DirectoryOperationResult:
    """
    Create a directory and its parents if needed.
    
    Args:
        path: Directory path to create
        exist_ok: If True, don't error if directory already exists
        
    Returns:
        DirectoryOperationResult
    """
    try:
        os.makedirs(path, exist_ok=exist_ok)

        if exist_ok and os.path.isdir(path):
            # Check if it already existed
            return DirectoryOperationResult(
                success=True,
                status=DirectoryStatus.SUCCESS,
                path=path,
                message=f"Directory ensured: {path}"
            )

        return DirectoryOperationResult(
            success=True,
            status=DirectoryStatus.SUCCESS,
            path=path,
            message=f"Directory created: {path}"
        )

    except PermissionError as e:
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.PERMISSION_DENIED,
            path=path,
            message=f"Permission denied: {e}"
        )
    except Exception as e:
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.ERROR,
            path=path,
            message=f"Failed to create directory: {e}"
        )


def delete_directory(
    path: str,
    recursive: bool = False
) -> DirectoryOperationResult:
    """
    Delete a directory.
    
    Args:
        path: Directory path to delete
        recursive: If True, delete contents recursively
        
    Returns:
        DirectoryOperationResult
    """
    if not os.path.exists(path):
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.NOT_FOUND,
            path=path,
            message=f"Directory not found: {path}"
        )

    if not os.path.isdir(path):
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.ERROR,
            path=path,
            message=f"Path is not a directory: {path}"
        )

    try:
        if recursive:
            shutil.rmtree(path)
            return DirectoryOperationResult(
                success=True,
                status=DirectoryStatus.SUCCESS,
                path=path,
                message=f"Directory deleted recursively: {path}"
            )
        else:
            os.rmdir(path)  # Only works if empty
            return DirectoryOperationResult(
                success=True,
                status=DirectoryStatus.SUCCESS,
                path=path,
                message=f"Directory deleted: {path}"
            )

    except OSError as e:
        if "Directory not empty" in str(e):
            return DirectoryOperationResult(
                success=False,
                status=DirectoryStatus.NOT_EMPTY,
                path=path,
                message="Directory not empty. Use recursive=True to delete with contents."
            )
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.ERROR,
            path=path,
            message=f"Failed to delete directory: {e}"
        )
    except Exception as e:
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.ERROR,
            path=path,
            message=f"Failed to delete directory: {e}"
        )


def delete_file(path: str) -> DirectoryOperationResult:
    """
    Delete a file.
    
    Args:
        path: File path to delete
        
    Returns:
        DirectoryOperationResult
    """
    if not os.path.exists(path):
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.NOT_FOUND,
            path=path,
            message=f"File not found: {path}"
        )

    if os.path.isdir(path):
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.ERROR,
            path=path,
            message=f"Path is a directory, not a file: {path}"
        )

    try:
        os.remove(path)
        return DirectoryOperationResult(
            success=True,
            status=DirectoryStatus.SUCCESS,
            path=path,
            message=f"File deleted: {path}"
        )
    except PermissionError as e:
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.PERMISSION_DENIED,
            path=path,
            message=f"Permission denied: {e}"
        )
    except Exception as e:
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.ERROR,
            path=path,
            message=f"Failed to delete file: {e}"
        )


def move_path(
    source: str,
    destination: str
) -> DirectoryOperationResult:
    """
    Move a file or directory to a new location.
    
    Args:
        source: Source path
        destination: Destination path
        
    Returns:
        DirectoryOperationResult
    """
    if not os.path.exists(source):
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.NOT_FOUND,
            path=source,
            message=f"Source not found: {source}"
        )

    try:
        # Ensure parent directory exists
        dest_parent = os.path.dirname(os.path.abspath(destination))
        if dest_parent:
            os.makedirs(dest_parent, exist_ok=True)

        shutil.move(source, destination)

        return DirectoryOperationResult(
            success=True,
            status=DirectoryStatus.SUCCESS,
            path=source,
            destination=destination,
            message=f"Moved: {source} -> {destination}"
        )

    except PermissionError as e:
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.PERMISSION_DENIED,
            path=source,
            message=f"Permission denied: {e}"
        )
    except Exception as e:
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.ERROR,
            path=source,
            message=f"Failed to move: {e}"
        )


# ============================================================================
# Directory Information
# ============================================================================

def get_directory_info(path: str) -> DirectoryInfo:
    """
    Get information about a directory.
    
    Args:
        path: Directory path
        
    Returns:
        DirectoryInfo with counts and size
    """
    if not os.path.isdir(path):
        return DirectoryInfo(path=path, exists=False)

    file_count = 0
    subdir_count = 0
    total_size = 0
    is_empty = True

    try:
        for entry in os.scandir(path):
            if entry.name.startswith('.'):
                continue
            is_empty = False

            if entry.is_file():
                file_count += 1
                total_size += entry.stat().st_size
            elif entry.is_dir():
                subdir_count += 1
                # Recursively count
                sub_info = get_directory_info(entry.path)
                file_count += sub_info.file_count
                subdir_count += sub_info.subdir_count
                total_size += sub_info.total_size
    except OSError:
        pass

    return DirectoryInfo(
        path=path,
        exists=True,
        is_empty=is_empty,
        file_count=file_count,
        subdir_count=subdir_count,
        total_size=total_size
    )


def get_directory_size(path: str) -> int:
    """
    Calculate total size of a directory.
    
    Args:
        path: Directory path
        
    Returns:
        Total size in bytes
    """
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            # Skip hidden directories
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]

            for f in filenames:
                if f.startswith('.'):
                    continue
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total


# ============================================================================
# Tree Generation (Agent-friendly compact format)
# ============================================================================

def generate_tree(
    path: str,
    max_depth: int = 3,
    max_entries: int = 200,
    with_stats: bool = False,
    prefix: str = "",
    exclude_dirs: list[str] | None = None,
    _state: dict | None = None,
) -> str:
    """
    Generate compact tree representation of directory.
    
    Uses 2-space indentation instead of ASCII decorators to save tokens.
    Supports max_entries limit and optional directory stats.
    
    Args:
        path: Root directory path
        max_depth: Maximum depth to display
        max_entries: Maximum number of entries to show (default 200)
        with_stats: If True, shows file count and size for directories
        prefix: Prefix for indentation (internal use)
        exclude_dirs: Directory names to exclude
        _state: Internal state for tracking entries across recursion
        
    Returns:
        Compact tree string
    """
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDED_DIRS

    if not os.path.isdir(path):
        return f"Not a directory: {path}"

    # Initialize state on first call
    if _state is None:
        _state = {"count": 0, "truncated": False, "total": 0}
        # Pre-count total for truncation message
        try:
            _state["total"] = len([
                e for e in os.scandir(path)
                if not e.name.startswith('.') and
                (not e.is_dir() or e.name not in exclude_dirs)
            ])
            # Add recursive count if depth allows
            # Note: this is approximate, we don't scan full tree
        except OSError:
            pass

    result = []
    base_name = os.path.basename(path) or path

    # Count files in this directory for stats
    file_count, subdir_count, _ = _count_entries(path, exclude_dirs) if with_stats else (0, 0, 0)
    stats_str = _format_dir_stats(file_count, subdir_count) if with_stats else ""

    if prefix:
        result.append(f"{prefix}{base_name}/{stats_str}")
    else:
        result.append(f"{base_name}/{stats_str}")
    _state["count"] += 1

    if _state["truncated"]:
        return '\n'.join(result)

    try:
        entries = list(os.scandir(path))
        # Sort by priority: directories first, then by file type, then alphabetically
        entries.sort(key=_get_entry_priority)

        # Filter out hidden and excluded
        visible_entries = [
            e for e in entries
            if not e.name.startswith('.') and
            (not e.is_dir() or e.name not in exclude_dirs)
        ]

        for i, entry in enumerate(visible_entries):
            if _state["count"] >= max_entries:
                remaining = len(visible_entries) - i
                # Try to estimate total remaining including subdirs
                result.append(
                    f"{prefix}  ... ({remaining}+ more entries hidden)\n"
                    f"  Tip: Use list_directory(path=\"...\", filter=\"*.py\") to narrow results, "
                    f"or increase max_entries to see more."
                )
                _state["truncated"] = True
                break

            child_prefix = f"{prefix}  "

            if entry.is_dir():
                if max_depth > 1:
                    subtree = generate_tree(
                        entry.path,
                        max_depth - 1,
                        max_entries,
                        with_stats,
                        child_prefix,
                        exclude_dirs,
                        _state
                    )
                    # Keep all lines from subtree (directory name is shown by generate_tree)
                    result.extend(subtree.split('\n'))
                    if _state["truncated"]:
                        break
                else:
                    # Depth limit reached, show directory name only
                    child_file_count, child_subdir_count, _ = _count_entries(entry.path, exclude_dirs) if with_stats else (0, 0, 0)
                    child_stats = _format_dir_stats(child_file_count, child_subdir_count) if with_stats else ""
                    result.append(f"{child_prefix}{entry.name}/{child_stats}")
                    _state["count"] += 1
            else:
                size_str = f"  {_format_size(entry.stat().st_size)}" if with_stats else ""
                result.append(f"{child_prefix}{entry.name}{size_str}")
                _state["count"] += 1

    except OSError as e:
        result.append(f"{prefix}  [Error: {e}]")

    return '\n'.join(result)


# ============================================================================
# Convenience Functions
# ============================================================================

def ensure_directory(path: str) -> bool:
    """Ensure directory exists, create if needed. Returns success."""
    result = create_directory(path, exist_ok=True)
    return result.success


def is_empty_directory(path: str) -> bool:
    """Check if directory is empty (ignoring hidden files)."""
    if not os.path.isdir(path):
        return False

    try:
        for entry in os.scandir(path):
            if not entry.name.startswith('.'):
                return False
        return True
    except OSError:
        return False
