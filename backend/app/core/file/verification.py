"""
Core file verification utilities - Hash-based change detection and safe file operations.

This module provides utilities for verifying file integrity and safe editing
with concurrent modification detection.
"""

import logging
import os

from app.core.file.schemas import FileWriteResult

from .io import get_file_info, read_file, write_file
from .models import FileInfo

# FileStats is an alias for FileInfo for backward compatibility
FileStats = FileInfo

logger = logging.getLogger(__name__)


def safe_read_with_hash(file_path: str) -> tuple[str, str, FileInfo]:
    """
    Read file and return content with hash for change detection.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Tuple of (content, encoding, file_info)
    """
    info = get_file_info(file_path)
    result = read_file(file_path)

    if not result.success:
        # Return empty content but still provide stats
        return "", info.encoding, info

    return result.content, result.encoding, info


def verify_file_hash(file_path: str, expected_hash: str) -> bool:
    """
    Verify file hasn't changed since last read.
    
    Args:
        file_path: Path to the file
        expected_hash: Expected MD5 hash
        
    Returns:
        True if hash matches, False otherwise
    """
    try:
        current_info = get_file_info(file_path)
        return current_info.content_hash == expected_hash
    except Exception:
        return False


def write_file_with_verification(
    content: str,
    file_path: str,
    expected_hash: str | None = None
) -> FileWriteResult:
    """
    Write file with optional hash verification for concurrent modification detection.
    
    This is a higher-level wrapper over write_file that adds hash verification
    for optimistic locking during concurrent edits.
    
    Args:
        content: Content to write
        file_path: Target file path
        expected_hash: Expected hash of file before modification (None = skip verification)
        
    Returns:
        Dict with success status and metadata
    """
    try:
        # Verify file hasn't changed (for edits)
        if expected_hash and os.path.exists(file_path):
            if not verify_file_hash(file_path, expected_hash):
                return FileWriteResult(
                    success=False,
                    error="FILE_MODIFIED",
                    message="File was modified by another process. Please re-read and try again."
                )

        # Use core write operation
        result = write_file(file_path, content)

        if result.success:
            return FileWriteResult(
                success=True,
                path=file_path,
                new_hash=result.new_hash,
                bytes_written=result.bytes_written
            )
        else:
            return FileWriteResult(
                success=False,
                error="WRITE_FAILED",
                message=result.error_message or "Unknown write error"
            )

    except Exception as e:
        logger.error(f"Failed to write file {file_path}: {e}")
        # Clean up temp file if exists
        temp_path = file_path + ".tmp"
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)
        return FileWriteResult(
            success=False,
            error="WRITE_FAILED",
            message=str(e)
        )


def apply_edit_with_verification(
    file_path: str,
    old_string: str,
    new_string: str,
    expected_hash: str | None = None,
    allow_multiple: bool = False
) -> FileWriteResult:
    """
    Apply string replacement edit with hash verification.
    
    Args:
        file_path: Target file path
        old_string: String to find and replace
        new_string: Replacement string
        expected_hash: Expected hash of file before modification
        allow_multiple: Replace all occurrences
        
    Returns:
        Dict with success status, change count, and metadata
    """
    try:
        # Read current content
        content, encoding, info = safe_read_with_hash(file_path)

        # Verify hash if provided
        if expected_hash and info.content_hash != expected_hash:
            return FileWriteResult(
                success=False,
                error="FILE_MODIFIED",
                message="File was modified by another process. Please re-read and try again.",
                current_hash=info.content_hash
            )

        # Apply replacement
        if allow_multiple:
            new_content = content.replace(old_string, new_string)
            change_count = content.count(old_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
            change_count = 1 if old_string in content else 0

        if change_count == 0:
            return FileWriteResult(
                success=False,
                error="NOT_FOUND",
                message=f"Could not find target text in file: {old_string[:50]}..."
            )

        # Write with verification
        write_result = write_file_with_verification(
            new_content, file_path, expected_hash
        )

        if write_result["success"]:
            write_result["change_count"] = change_count

        return write_result

    except Exception as e:
        logger.error(f"Failed to apply edit to {file_path}: {e}")
        return FileWriteResult(
            success=False,
            error="EDIT_FAILED",
            message=str(e)
        )


# Convenience alias for backward compatibility
get_file_stats = get_file_info
