"""
Path Utilities

Provides safe path manipulation functions to prevent directory traversal attacks
and ensure consistent path handling across the application.
"""

import os
import re
from pathlib import Path
from typing import Optional


def normalize_path(path: str) -> str:
    """
    Normalize path separators to forward slashes and remove redundant separators.
    
    Args:
        path: Path to normalize
    
    Returns:
        Normalized path with forward slashes
    """
    return path.replace('\\', '/').replace('//', '/')


def safe_join(base_path: str, *paths: str) -> str:
    """
    Safely join paths, preventing directory traversal attacks.
    
    Args:
        base_path: Base directory path
        *paths: Path components to join
    
    Returns:
        Safe joined path
    
    Raises:
        ValueError: If the resulting path escapes base_path
    
    Examples:
        >>> safe_join('/home/user', 'docs', 'file.txt')
        '/home/user/docs/file.txt'
        >>> safe_join('/home/user', '../etc/passwd')  # Raises ValueError
    """
    base_path = os.path.abspath(base_path)
    joined = os.path.join(base_path, *paths)
    resolved = os.path.abspath(joined)
    
    # Ensure resolved path starts with base_path
    if not resolved.startswith(base_path):
        raise ValueError(f"Path traversal detected: {paths}")
    
    return resolved


def is_safe_path(base_path: str, target_path: str) -> bool:
    """
    Check if target_path is within base_path (prevents directory traversal).
    
    Args:
        base_path: Base directory path
        target_path: Path to check
    
    Returns:
        True if target_path is within base_path
    """
    try:
        base = Path(base_path).resolve()
        target = Path(target_path).resolve()
        return str(target).startswith(str(base))
    except (ValueError, OSError):
        return False


def ensure_dir(path: str) -> str:
    """
    Ensure directory exists, creating it if necessary.
    
    Args:
        path: Directory path
    
    Returns:
        The path (unchanged)
    """
    os.makedirs(path, exist_ok=True)
    return path


def get_file_extension(file_path: str) -> str:
    """
    Get file extension in lowercase without the dot.
    
    Args:
        file_path: Path to file
    
    Returns:
        Lowercase extension (e.g., 'py', 'txt')
    """
    return Path(file_path).suffix.lstrip('.').lower()


def get_filename_without_ext(file_path: str) -> str:
    """
    Get filename without extension.
    
    Args:
        file_path: Path to file
    
    Returns:
        Filename without extension
    """
    return Path(file_path).stem


def sanitize_filename(filename: str, replacement: str = '_') -> str:
    """
    Sanitize filename by removing or replacing unsafe characters.
    
    Args:
        filename: Original filename
        replacement: Character to replace unsafe characters with
    
    Returns:
        Sanitized filename
    """
    # Remove path separators and null bytes
    unsafe = ['\\', '/', '\x00', '\n', '\r', '\t']
    result = filename
    for char in unsafe:
        result = result.replace(char, replacement)
    
    # Remove other special characters
    result = re.sub(r'[<>:"|?*]', replacement, result)
    
    # Limit length
    if len(result) > 255:
        name, ext = os.path.splitext(result)
        result = name[:255 - len(ext)] + ext
    
    # Don't allow hidden files or reserved names on Windows
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3',
                'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}
    
    base = Path(result).stem.upper()
    if base in reserved:
        result = replacement + result
    
    return result


def get_relative_path(path: str, start: str) -> str:
    """
    Get relative path from start to path.
    
    Args:
        path: Target path
        start: Start directory
    
    Returns:
        Relative path
    """
    try:
        return os.path.relpath(path, start)
    except ValueError:
        # On Windows, paths on different drives can't be made relative
        return path


def get_absolute_path(path: str) -> str:
    """
    Get absolute path, expanding user directory (~).
    
    Args:
        path: Path to convert
    
    Returns:
        Absolute path
    """
    return os.path.abspath(os.path.expanduser(path))


def find_files(
    directory: str,
    pattern: Optional[str] = None,
    extensions: Optional[list[str]] = None,
    recursive: bool = True
) -> list[str]:
    """
    Find files in directory matching criteria.
    
    Args:
        directory: Directory to search
        pattern: Optional regex pattern to match filenames
        extensions: Optional list of extensions to include (e.g., ['.py', '.txt'])
        recursive: Whether to search recursively
    
    Returns:
        List of matching file paths
    """
    matches = []
    
    if recursive:
        for root, _dirs, files in os.walk(directory):
            for filename in files:
                filepath = os.path.join(root, filename)
                if _matches_criteria(filename, filepath, pattern, extensions):
                    matches.append(filepath)
    else:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath) and _matches_criteria(filename, filepath, pattern, extensions):
                matches.append(filepath)
    
    return matches


def _matches_criteria(
    filename: str,
    filepath: str,
    pattern: Optional[str],
    extensions: Optional[list[str]]
) -> bool:
    """Helper to check if file matches search criteria."""
    if extensions is not None:
        ext = Path(filename).suffix.lower()
        if ext not in [e.lower() for e in extensions]:
            return False
    
    if pattern is not None:
        if not re.search(pattern, filename):
            return False
    
    return True


def get_unique_filename(directory: str, filename: str) -> str:
    """
    Generate a unique filename by appending a number if file exists.
    
    Args:
        directory: Target directory
        filename: Desired filename
    
    Returns:
        Unique filename
    """
    base, ext = os.path.splitext(filename)
    counter = 1
    result = filename
    
    while os.path.exists(os.path.join(directory, result)):
        result = f"{base}_{counter}{ext}"
        counter += 1
    
    return result


def is_path_readable(path: str) -> bool:
    """Check if path is readable."""
    return os.path.exists(path) and os.access(path, os.R_OK)


def is_path_writable(path: str) -> bool:
    """Check if path is writable (file exists and writable, or directory allows creation)."""
    if os.path.exists(path):
        return os.access(path, os.W_OK)
    
    # Check if parent directory is writable
    parent = os.path.dirname(path) or '.'
    return os.path.isdir(parent) and os.access(parent, os.W_OK)
