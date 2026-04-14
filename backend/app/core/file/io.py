"""
Core file I/O operations - Domain-agnostic file read/write utilities.

This module provides the foundational file operations used by the tool layer.
All functions are pure I/O without business logic (no validation, no formatting).
"""

import hashlib
import logging
import os
from collections.abc import Iterator
from typing import Optional

from .models import FileInfo, FileStatus, ReadResult, WriteResult, PaginationInfo

logger = logging.getLogger(__name__)

# Constants
LARGE_FILE_THRESHOLD = 10 * 1024 * 1024  # 10MB
DEFAULT_PAGE_SIZE = 100


# ============================================================================
# Encoding Detection
# ============================================================================

def detect_encoding(file_path: str) -> str:
    """
    Detect file encoding by trying common encodings.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Detected encoding name (default: utf-8)
    """
    encodings = ["utf-8", "latin-1", "utf-16", "ascii", "gbk", "big5"]
    
    for encoding in encodings:
        try:
            with open(file_path, encoding=encoding) as f:
                f.read(1024)  # Test first 1KB
                return encoding
        except UnicodeDecodeError:
            continue
    
    logger.warning(f"Could not detect encoding for {file_path}, defaulting to utf-8")
    return "utf-8"


# ============================================================================
# File Statistics
# ============================================================================

def compute_file_hash(file_path: str) -> str:
    """
    Compute MD5 hash of file content.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Hex digest of MD5 hash (first 16 chars)
    """
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


def get_file_info(file_path: str) -> FileInfo:
    """
    Get comprehensive file information.
    
    Args:
        file_path: Path to the file
        
    Returns:
        FileInfo with size, lines, encoding, hash
    """
    if not os.path.exists(file_path):
        return FileInfo(
            path=file_path,
            size=0,
            total_lines=0,
            encoding="utf-8",
            content_hash="",
            exists=False
        )
    
    size = os.path.getsize(file_path)
    encoding = detect_encoding(file_path)
    content_hash = compute_file_hash(file_path)
    
    # Count lines
    total_lines = 0
    with open(file_path, "rb") as f:
        for _ in f:
            total_lines += 1
    
    return FileInfo(
        path=file_path,
        size=size,
        total_lines=total_lines,
        encoding=encoding,
        content_hash=content_hash,
        is_large=size > LARGE_FILE_THRESHOLD,
        is_binary=_is_binary_file(file_path),
        exists=True
    )


def _is_binary_file(file_path: str) -> bool:
    """Check if file is binary by sampling first 4KB."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(4096)
            if b"\x00" in chunk:
                return True
            # Try decode as text
            try:
                chunk.decode("utf-8")
                return False
            except UnicodeDecodeError:
                return True
    except Exception:
        return True


# ============================================================================
# Read Operations
# ============================================================================

def read_file(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    encoding: Optional[str] = None,
) -> ReadResult:
    """
    Read file content with optional line range.
    
    Args:
        file_path: Path to the file
        start_line: 1-indexed starting line (None = from beginning)
        end_line: 1-indexed ending line (None = to end)
        encoding: Specific encoding (None = auto-detect)
        
    Returns:
        ReadResult with content and metadata
    """
    # Check existence
    if not os.path.exists(file_path):
        return ReadResult(
            content="",
            encoding=encoding or "utf-8",
            status=FileStatus.NOT_FOUND,
            metadata=FileInfo(path=file_path, size=0, total_lines=0, 
                            encoding="utf-8", content_hash="", exists=False),
            error_message=f"File not found: {file_path}"
        )
    
    # Get file info
    try:
        info = get_file_info(file_path)
    except Exception as e:
        return ReadResult(
            content="",
            encoding=encoding or "utf-8",
            status=FileStatus.ERROR,
            metadata=FileInfo(path=file_path, size=0, total_lines=0,
                            encoding="utf-8", content_hash="", exists=False),
            error_message=f"Failed to get file info: {e}"
        )
    
    # Use detected encoding if not specified
    if encoding is None:
        encoding = info.encoding
    
    # Determine read range
    start_idx = (start_line - 1) if start_line else 0
    end_idx = (end_line - 1) if end_line else None
    
    try:
        # For small files or full read, read all at once
        if not info.is_large and start_idx == 0 and end_idx is None:
            with open(file_path, encoding=encoding) as f:
                content = f.read()
            return ReadResult(
                content=content,
                encoding=encoding,
                status=FileStatus.SUCCESS,
                metadata=info
            )
        
        # For large files or paginated reads, use streaming
        content = _read_lines_range(file_path, encoding, start_idx, end_idx)
        
        return ReadResult(
            content=content,
            encoding=encoding,
            status=FileStatus.SUCCESS,
            metadata=info
        )
        
    except UnicodeDecodeError as e:
        return ReadResult(
            content="",
            encoding=encoding,
            status=FileStatus.ENCODING_ERROR,
            metadata=info,
            error_message=f"Encoding error: {e}"
        )
    except Exception as e:
        return ReadResult(
            content="",
            encoding=encoding,
            status=FileStatus.ERROR,
            metadata=info,
            error_message=f"Read error: {e}"
        )


def _read_lines_range(
    file_path: str,
    encoding: str,
    start_idx: int = 0,
    end_idx: Optional[int] = None
) -> str:
    """
    Read specific line range from file efficiently.
    
    Args:
        file_path: Path to the file
        encoding: File encoding
        start_idx: 0-indexed starting line
        end_idx: 0-indexed ending line (None = to end)
        
    Returns:
        Content of specified line range
    """
    lines = []
    with open(file_path, encoding=encoding) as f:
        for i, line in enumerate(f):
            if i < start_idx:
                continue
            if end_idx is not None and i > end_idx:
                break
            lines.append(line)
    return "".join(lines)


def read_lines_streaming(
    file_path: str,
    start_line: int = 1,
    limit: Optional[int] = None,
) -> Iterator[str]:
    """
    Stream file lines one by one (memory efficient).
    
    Args:
        file_path: Path to the file
        start_line: 1-indexed starting line
        limit: Maximum lines to yield (None = all)
        
    Yields:
        Lines from the file
    """
    encoding = detect_encoding(file_path)
    start_idx = start_line - 1
    end_idx = (start_idx + limit) if limit else None
    
    with open(file_path, encoding=encoding) as f:
        for i, line in enumerate(f):
            if i < start_idx:
                continue
            if end_idx is not None and i >= end_idx:
                break
            yield line


# ============================================================================
# Write Operations
# ============================================================================

def write_file(
    file_path: str,
    content: str,
    encoding: str = "utf-8",
    create_dirs: bool = True,
) -> WriteResult:
    """
    Write content to file atomically.
    
    Args:
        file_path: Target file path
        content: Content to write
        encoding: File encoding (default: utf-8)
        create_dirs: Create parent directories if needed
        
    Returns:
        WriteResult with status and metadata
    """
    try:
        # Create parent directories
        if create_dirs:
            parent = os.path.dirname(os.path.abspath(file_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        
        # Write atomically using temp file
        temp_path = file_path + ".tmp"
        with open(temp_path, "w", encoding=encoding) as f:
            f.write(content)
        
        # Atomic rename
        os.replace(temp_path, file_path)
        
        # Compute new hash
        new_hash = compute_file_hash(file_path)
        
        return WriteResult(
            path=file_path,
            status=FileStatus.SUCCESS,
            bytes_written=len(content.encode(encoding)),
            new_hash=new_hash
        )
        
    except PermissionError as e:
        return WriteResult(
            path=file_path,
            status=FileStatus.PERMISSION_DENIED,
            error_message=f"Permission denied: {e}"
        )
    except Exception as e:
        return WriteResult(
            path=file_path,
            status=FileStatus.ERROR,
            error_message=f"Write error: {e}"
        )


def append_to_file(
    file_path: str,
    content: str,
    encoding: str = "utf-8",
) -> WriteResult:
    """
    Append content to existing file.
    
    Args:
        file_path: Target file path
        content: Content to append
        encoding: File encoding
        
    Returns:
        WriteResult with status
    """
    try:
        with open(file_path, "a", encoding=encoding) as f:
            f.write(content)
        
        new_hash = compute_file_hash(file_path)
        
        return WriteResult(
            path=file_path,
            status=FileStatus.SUCCESS,
            bytes_written=len(content.encode(encoding)),
            new_hash=new_hash
        )
        
    except Exception as e:
        return WriteResult(
            path=file_path,
            status=FileStatus.ERROR,
            error_message=f"Append error: {e}"
        )


# ============================================================================
# Convenience Functions
# ============================================================================

def file_exists(file_path: str) -> bool:
    """Check if file exists."""
    return os.path.isfile(file_path)


def ensure_dir(directory: str) -> bool:
    """Ensure directory exists, create if needed."""
    try:
        os.makedirs(directory, exist_ok=True)
        return True
    except Exception:
        return False


def get_pagination_info(
    file_path: str,
    start_line: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> PaginationInfo:
    """
    Get pagination info for a file.
    
    Args:
        file_path: Path to the file
        start_line: 1-indexed starting line
        page_size: Lines per page
        
    Returns:
        PaginationInfo with metadata
    """
    info = get_file_info(file_path)
    end_line = min(start_line + page_size - 1, info.total_lines)
    
    return PaginationInfo(
        total_lines=info.total_lines,
        start_line=start_line,
        end_line=end_line,
        has_more=end_line < info.total_lines,
        page_size=page_size
    )
