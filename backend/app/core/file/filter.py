import logging
import os
import re

from app.constants import (
    DEFAULT_EXCLUDED_DIRS,
    DEFAULT_EXCLUDED_EXTENSIONS,
    DEFAULT_EXCLUDED_FILES,
)

logger = logging.getLogger(__name__)


def is_encrypted_path(file_path: str, pattern=r"[a-f0-9]{8,}") -> bool:
    """Check if path contains a hash-like pattern."""
    # Normalize and split to check each component
    parts = file_path.replace("\\", "/").split("/")
    for part in parts:
        if re.search(pattern, part):
            return True
    return False


def is_ignored_path(path: str) -> bool:
    """
    Check if a path (file or directory) should be ignored based on its components.
    Unified check for hidden patterns and blacklisted directories/files.
    """
    if not path:
        return False

    # Normalize and split path
    path = path.replace("\\", "/")
    parts = path.split("/")

    for part in parts:
        if not part:
            continue
        # Hidden or special prefixes (., ~, _)
        if part.startswith((".", "~", "_")):
            return True
        # Blacklisted directory names
        if part in DEFAULT_EXCLUDED_DIRS:
            return True

    # Check for excluded files or extensions
    file_name = parts[-1] if parts else ""
    if file_name:
        # Check explicit filename blacklist
        if any(file_name.endswith(ef) for ef in DEFAULT_EXCLUDED_FILES):
            return True
        # Check extension blacklist
        ext = os.path.splitext(file_name)[1].lower()
        if ext in DEFAULT_EXCLUDED_EXTENSIONS:
            return True

    return False


def get_grep_exclude_args() -> list[str]:
    """
    Generate a list of grep command line arguments to exclude standard directories and files.
    """
    args = []
    # Directories
    for d in DEFAULT_EXCLUDED_DIRS:
        args.append(f"--exclude-dir={d}")

    # Hidden directories and files
    args.append("--exclude-dir=.*")
    args.append("--exclude=.*")

    # Specific files
    for f in DEFAULT_EXCLUDED_FILES:
        args.append(f"--exclude={f}")

    return args


def get_ripgrep_exclude_args() -> list[str]:
    """
    Generate a list of ripgrep (rg) command line arguments to exclude standard directories and files.
    """
    args = []
    # Directories and Files
    for d in DEFAULT_EXCLUDED_DIRS:
        args.extend(["-g", f"!{d}"])

    for f in DEFAULT_EXCLUDED_FILES:
        args.extend(["-g", f"!{f}"])

    return args
