"""
Standardized directory operations using the new File Center core.
All traversal and tree logic is now delegated to traverser.py and tree.py.
"""

import logging
import os
import shutil
from collections.abc import Iterator

from .schemas import (
    DirectoryEntry,
    DirectoryInfo,
    DirectoryOperationResult,
    DirectoryStatus,
)
from .traverser import FileTraverser
from .tree import TreeService

logger = logging.getLogger(__name__)


# ============================================================================
# Directory Listing & Tree (Delegated to TreeService & Traverser)
# ============================================================================


def list_directory(
    path: str,
    exclude_dirs: list[str] | None = None,
    recursive: bool = False,
    max_depth: int | None = None,
    filter_pattern: str | None = None,
) -> Iterator[DirectoryEntry]:
    """
    List directory entries with optional recursion and filtering.
    Now delegated to TreeService for consistency.
    """
    # Note: list_directory usually returns DirectoryEntry objects
    # FileTraverser.list_entries returns os.DirEntry for performance.
    # We bridge them here for backward compatibility.
    try:
        entries = FileTraverser.list_entries(path, exclude_dirs)
        for entry in entries:
            stat = entry.stat()
            yield DirectoryEntry(
                name=entry.name,
                path=str(entry.path),
                is_dir=entry.is_dir(),
                size=stat.st_size if entry.is_file() else 0,
            )
    except Exception as e:
        logger.warning(f"Cannot list directory {path}: {e}")


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
    Generate compact tree representation. Delegated to TreeService.
    """
    return TreeService.get_text_tree(
        path=path,
        max_depth=max_depth,
        max_entries=max_entries,
        prefix=prefix,
        exclude_dirs=exclude_dirs,
        _state=_state,
        with_stats=with_stats,
    )


# ============================================================================
# Directory Operations (Atomic)
# ============================================================================


def create_directory(path: str, exist_ok: bool = True) -> DirectoryOperationResult:
    """Create a directory and its parents if needed."""
    try:
        os.makedirs(path, exist_ok=exist_ok)
        return DirectoryOperationResult(
            success=True,
            status=DirectoryStatus.SUCCESS,
            path=path,
            message=f"Directory ensured: {path}",
        )
    except Exception as e:
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.ERROR,
            path=path,
            message=f"Failed to create directory: {e}",
        )


def delete_directory(path: str, recursive: bool = False) -> DirectoryOperationResult:
    """Delete a directory."""
    if not os.path.isdir(path):
        return DirectoryOperationResult(
            success=False,
            status=DirectoryStatus.NOT_FOUND,
            path=path,
            message="Not found",
        )
    try:
        if recursive:
            shutil.rmtree(path)
        else:
            os.rmdir(path)
        return DirectoryOperationResult(success=True, status=DirectoryStatus.SUCCESS, path=path, message="Deleted")
    except Exception as e:
        return DirectoryOperationResult(success=False, status=DirectoryStatus.ERROR, path=path, message=str(e))


def delete_file(path: str) -> DirectoryOperationResult:
    """Delete a file."""
    try:
        os.remove(path)
        return DirectoryOperationResult(success=True, status=DirectoryStatus.SUCCESS, path=path, message="Deleted")
    except Exception as e:
        return DirectoryOperationResult(success=False, status=DirectoryStatus.ERROR, path=path, message=str(e))


def move_path(source: str, destination: str) -> DirectoryOperationResult:
    """Move a file or directory."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
        shutil.move(source, destination)
        return DirectoryOperationResult(
            success=True,
            status=DirectoryStatus.SUCCESS,
            path=source,
            destination=destination,
            message="Moved",
        )
    except Exception as e:
        return DirectoryOperationResult(success=False, status=DirectoryStatus.ERROR, path=source, message=str(e))


# ============================================================================
# Directory Information
# ============================================================================


def get_directory_info(path: str) -> DirectoryInfo:
    """Get information about a directory using unified traversal."""
    if not os.path.isdir(path):
        return DirectoryInfo(path=path, exists=False)

    file_count = 0
    total_size = 0
    is_empty = True

    # Use unified walker to count files and calculate size
    for full_path in FileTraverser.walk(path):
        is_empty = False
        file_count += 1
        try:
            total_size += os.path.getsize(full_path)
        except OSError:
            pass

    return DirectoryInfo(
        path=path,
        exists=True,
        is_empty=is_empty,
        file_count=file_count,
        subdir_count=0,  # Simplified for now
        total_size=total_size,
    )


def get_directory_size(path: str) -> int:
    """Calculate total size using unified traversal."""
    total = 0
    for full_path in FileTraverser.walk(path):
        try:
            total += os.stat(full_path).st_size
        except OSError:
            pass
    return total


def ensure_directory(path: str) -> bool:
    """Ensure directory exists."""
    result = create_directory(path, exist_ok=True)
    return result.success


def is_empty_directory(path: str) -> bool:
    """Check if directory is empty using unified traversal."""
    try:
        for _ in FileTraverser.list_entries(path):
            return False
        return True
    except Exception:
        return False
