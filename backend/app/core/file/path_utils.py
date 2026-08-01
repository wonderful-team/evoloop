import logging

"""
Path-specific utilities for the File Center.
Consolidated from app.utils.path and other legacy locations.
"""

import os
import re
from pathlib import Path
logger = logging.getLogger(__name__)

def normalize_path(path: str) -> str:
    """Normalize path separators to forward slashes."""
    return path.replace('\\', '/').replace('//', '/')

def safe_join(base_path: str, *paths: str) -> str:
    """Safely join paths, preventing directory traversal attacks."""
    base_path = os.path.abspath(base_path)
    joined = os.path.join(base_path, *paths)
    resolved = os.path.abspath(joined)
    
    if not resolved.startswith(base_path):
        raise ValueError(f"Path traversal detected: {paths}")
    
    return resolved

def is_safe_path(base_path: str, target_path: str) -> bool:
    """Check if target_path is within base_path."""
    try:
        base = Path(base_path).resolve()
        target = Path(target_path).resolve()
        return str(target).startswith(str(base))
    except (ValueError, OSError):
        return False

def sanitize_filename(filename: str, replacement: str = '_') -> str:
    """Sanitize filename by removing or replacing unsafe characters."""
    # Remove path separators and null bytes
    unsafe = ['\\', '/', '\x00', '\n', '\r', '\t']
    result = filename
    for char in unsafe:
        result = result.replace(char, replacement)
    
    # Remove other special characters
    result = re.sub(r'[<>:"|?*]', replacement, result)
    
    # Limit length (standard 255 for most FS)
    if len(result) > 255:
        name, ext = os.path.splitext(result)
        result = name[:255 - len(ext)] + ext
    
    return result

def get_unique_filename(directory: str, filename: str) -> str:
    """Generate a unique filename by appending a number if file exists."""
    base, ext = os.path.splitext(filename)
    counter = 1
    result = filename
    
    while os.path.exists(os.path.join(directory, result)):
        result = f"{base}_{counter}{ext}"
        counter += 1
    
    return result

def get_relative_path(path: str, start: str) -> str:
    """Get relative path from start to path."""
    try:
        return os.path.relpath(path, start)
    except ValueError:
        return path

def get_absolute_path(path: str) -> str:
    """Get absolute path, expanding user directory (~)."""
    return os.path.abspath(os.path.expanduser(path))

def is_path_readable(path: str) -> bool:
    """Check if path is readable."""
    return os.path.exists(path) and os.access(path, os.R_OK)

def is_path_writable(path: str) -> bool:
    """Check if path is writable."""
    if os.path.exists(path):
        return os.access(path, os.W_OK)
    
    # Check if parent directory is writable
    parent = os.path.dirname(path) or '.'
    return os.path.isdir(parent) and os.access(parent, os.W_OK)

def cleanup_file(filepath: str | None) -> None:
    """Safely remove a file if it exists."""
    if filepath and os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)
