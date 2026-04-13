"""
Core directory operations - Domain-agnostic directory utilities.

This module provides foundational directory operations used by the tool layer.
"""

import logging
import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional
from pydantic import BaseModel, Field

from app.constants import DEFAULT_EXCLUDED_DIRS
from app.utils.model_helpers import LegacyDictMixin

logger = logging.getLogger(__name__)


class DirectoryStatus(Enum):
    """Status of a directory operation."""
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    PERMISSION_DENIED = "permission_denied"
    NOT_EMPTY = "not_empty"
    ERROR = "error"


class DirectoryInfo(BaseModel, LegacyDictMixin):
    """Information about a directory."""
    path: str
    exists: bool
    is_empty: bool = False
    file_count: int = 0
    subdir_count: int = 0
    total_size: int = 0


class DirectoryOperationResult(BaseModel, LegacyDictMixin):
    """Result of a directory operation."""
    success: bool
    status: DirectoryStatus
    path: str
    message: str = ""
    destination: Optional[str] = None  # For move operations


class DirectoryEntry(BaseModel, LegacyDictMixin):
    """A single entry in directory listing."""
    name: str
    path: str
    is_dir: bool
    size: int = 0


# ============================================================================
# Directory Listing
# ============================================================================

def list_directory(
    path: str,
    recursive: bool = False,
    max_depth: Optional[int] = None,
    exclude_dirs: Optional[list[str]] = None,
) -> Iterator[DirectoryEntry]:
    """
    List directory entries with optional recursion.
    
    Args:
        path: Directory path
        recursive: Whether to list recursively
        max_depth: Maximum depth for recursion (None = unlimited)
        exclude_dirs: Directory names to exclude (e.g., ['node_modules', '.git'])
        
    Yields:
        DirectoryEntry objects
    """
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDED_DIRS
    
    if not os.path.isdir(path):
        return
    
    base_path = Path(path).resolve()
    
    if recursive:
        yield from _walk_directory(base_path, base_path, 0, max_depth, exclude_dirs)
    else:
        try:
            for entry in os.scandir(base_path):
                if entry.name.startswith('.'):
                    continue
                    
                stat = entry.stat()
                yield DirectoryEntry(
                    name=entry.name,
                    path=str(entry.path),
                    is_dir=entry.is_dir(),
                    size=stat.st_size if entry.is_file() else 0
                )
        except OSError as e:
            logger.warning(f"Cannot list directory {path}: {e}")


def _walk_directory(
    base_path: Path,
    current_path: Path,
    current_depth: int,
    max_depth: Optional[int],
    exclude_dirs: list[str]
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
                    exclude_dirs
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
                message=f"Directory not empty. Use recursive=True to delete with contents."
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
# Tree Generation
# ============================================================================

def generate_tree(
    path: str,
    max_depth: int = 3,
    prefix: str = "",
    exclude_dirs: Optional[list[str]] = None,
) -> str:
    """
    Generate ASCII tree representation of directory.
    
    Args:
        path: Root directory path
        max_depth: Maximum depth to display
        prefix: Prefix for indentation (internal use)
        exclude_dirs: Directory names to exclude
        
    Returns:
        ASCII tree string
    """
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDED_DIRS
    
    if not os.path.isdir(path):
        return f"Not a directory: {path}"
    
    result = []
    base_name = os.path.basename(path) or path
    result.append(base_name + "/")
    
    try:
        entries = list(os.scandir(path))
        # Sort: directories first, then alphabetically
        entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))
        
        # Filter out hidden and excluded
        visible_entries = [
            e for e in entries 
            if not e.name.startswith('.') and 
            (not e.is_dir() or e.name not in exclude_dirs)
        ]
        
        for i, entry in enumerate(visible_entries):
            is_last = (i == len(visible_entries) - 1)
            connector = "└── " if is_last else "├── "
            
            if entry.is_dir():
                result.append(f"{prefix}{connector}{entry.name}/")
                if max_depth > 1:
                    extension = "    " if is_last else "│   "
                    subtree = generate_tree(
                        entry.path, 
                        max_depth - 1, 
                        prefix + extension,
                        exclude_dirs
                    )
                    # Remove the root name from subtree (already added)
                    subtree_lines = subtree.split('\n')[1:]
                    result.extend(subtree_lines)
            else:
                result.append(f"{prefix}{connector}{entry.name}")
                
    except OSError as e:
        result.append(f"{prefix}[Error: {e}]")
    
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
