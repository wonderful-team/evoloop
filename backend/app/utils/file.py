import cgi
import logging
import mimetypes
import os
import re
import shutil
import tempfile
import urllib.request

from pathlib import Path
from urllib.parse import urlparse
from rapidfuzz import fuzz, process

from typing import Callable, Iterator
from app.constants import (
    BLACKLIST_FILE_EXTENSIONS,
    CODE_EXTENSION_MAP,
    DEFAULT_EXCLUDED_DIRS,
    DEFAULT_EXCLUDED_FILES,
    WHITELIST_FILE_EXTENSIONS,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Path Resolution & Navigation
# ============================================================================


def walk_tree(
    root_path: str,
    filter_func: Callable[[str], bool] | None = None,
    exclude_dirs: list[str] | None = None,
    max_depth: int | None = None,
    dir_filter: Callable[[str], bool] | None = None,
) -> Iterator[str]:
    """
    Standardized directory walker that yields valid file paths.
    Encapsulates directory pruning (node_modules, .git) and optional file filtering.

    Args:
        root_path: The root directory to walk.
        filter_func: A callable that takes an absolute file path and returns True if it should be included.
        exclude_dirs: A list of directory names to exclude (prune). Defaults to DEFAULT_EXCLUDED_DIRS.
        max_depth: Maximum depth to traverse. 0 means only root. None means infinite.
        dir_filter: A callable that takes an absolute directory path and returns True if it should be traversed.
    """
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDED_DIRS

    root_path = os.path.abspath(root_path)
    base_depth = root_path.rstrip(os.sep).count(os.sep)

    for root, dirs, files in os.walk(root_path):
        # Calculate depth
        current_depth = root.rstrip(os.sep).count(os.sep) - base_depth

        # Prune based on depth
        if max_depth is not None and current_depth >= max_depth:
            dirs[:] = []
            # We still yield files at this level (frontier), but stop going deeper.

        # Prune excluded directories
        # We combine standard name-based pruning with custom path-based filtering
        valid_dirs = []
        for d in dirs:
            if d in exclude_dirs or d.startswith("."):
                continue
            
            if dir_filter:
                dir_abs = os.path.join(root, d)
                if not dir_filter(dir_abs):
                    continue
            
            valid_dirs.append(d)
        
        dirs[:] = valid_dirs

        for f in files:
            # Skip hidden files (common convention)
            if f.startswith("."):
                continue

            full_path = os.path.join(root, f)

            if filter_func:
                if filter_func(full_path):
                    yield full_path
            else:
                yield full_path


def resolve_path(file_path: str, base_path: str | None = None) -> str | None:
    """
    Resolve a file path to an absolute local path.
    Handles URLs (by downloading), absolute paths, and paths relative to base_path.
    """
    if not file_path:
        return None

    # Handle URLs
    if file_path.startswith(("http://", "https://")):
        try:
            return ensure_local_path(file_path)
        except Exception as e:
            logger.error(f"Failed to resolve URL {file_path}: {e}")
            return None

    # Handle Absolute Paths
    if os.path.isabs(file_path):
        if os.path.exists(file_path):
            return file_path
        # If does not exist, check if it's meant to be relative to base_path (unlikely but possible cleanup)
        # But commonly we just return it if we are checking existence later.
        return file_path

    # Handle Relative Paths
    if base_path:
        # Prevent traversal above base_path if strict? For now, standard join.
        full_path = os.path.abspath(os.path.join(base_path, file_path))
        if os.path.exists(full_path):
            return full_path

        # Fuzzy/Smart resolution logic from legacy file_utils
        # Check specific edge cases
        repo_parts = base_path.split(os.path.sep)
        file_parts = file_path.split("/")

        # Overlap check (e.g. /users/repo/src + src/main.py)
        if file_parts and repo_parts and file_parts[0] == repo_parts[-1]:
            adjusted_path = os.path.join(base_path, *file_parts[1:])
            if os.path.exists(adjusted_path):
                return adjusted_path

        return full_path  # Return best guess

    return os.path.abspath(file_path)


def ensure_local_path(file_path: str) -> str:
    """
    If file_path is a URL, download it to a temporary file and return the temp path.
    Otherwise return the path as-is (assuming it is local).
    """
    if file_path.startswith(("http://", "https://")):
        try:
            req = urllib.request.Request(file_path, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                # 1. Try to get extension from URL
                parsed = urlparse(file_path)
                ext = os.path.splitext(parsed.path)[1]

                # 2. Try content-disposition
                if not ext:
                    cd = response.headers.get("Content-Disposition")
                    if cd:
                        _, params = cgi.parse_header(cd)
                        if "filename" in params:
                            ext = os.path.splitext(params["filename"])[1]

                # 3. Try content-type
                if not ext:
                    ct = response.headers.get("Content-Type")
                    if ct:
                        ext = mimetypes.guess_extension(ct.split(";")[0].strip())

                # 4. Default
                if not ext:
                    ext = ""

                fd, temp_path = tempfile.mkstemp(suffix=ext)
                os.close(fd)

                with open(temp_path, "wb") as out_file:
                    shutil.copyfileobj(response, out_file)

            logger.info(f"Downloaded {file_path} to {temp_path}")
            return temp_path
        except Exception as e:
            raise ValueError(f"Failed to download remote file: {e}")

    return file_path


def normalize_path(path: str) -> str:
    """Normalize path separators to forward slashes."""
    path = path.replace("\\", "/")
    return path.lstrip("/")


def get_file_ext(file: str) -> str:
    """Get file extension in lowercase."""
    return os.path.splitext(file)[1].lower()


def is_encrypted_path(file_path: str, pattern=r"[a-f0-9]{8,}") -> bool:
    """
    Check if path contains a hash-like pattern.
    Commonly used to detect build artifacts or versioned files.
    """
    for part in Path(file_path).parts:
        if re.search(pattern, part):
            return True
    return False


# ============================================================================
# File Content I/O
# ============================================================================


def get_file_encoding(file_path: str) -> str:
    """Attempt to detect file encoding."""
    encodings = ["utf-8", "latin-1", "utf-16", "ascii"]
    for encoding in encodings:
        try:
            with open(file_path, encoding=encoding) as f:
                f.read(100)
                return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def read_file_content(file_path: str, start_line: int | None = None, end_line: int | None = None) -> tuple[str, str]:
    """
    Read file content with auto encoding detection and optional line range.
    Returns (content, encoding).
    """
    encoding = get_file_encoding(file_path)
    try:
        with open(file_path, encoding=encoding) as f:
            if start_line is None and end_line is None:
                content = f.read()
            else:
                lines = f.readlines()
                total_lines = len(lines)

                # 1-based indexing correction
                start = max(0, start_line - 1) if start_line else 0
                end = min(total_lines, end_line) if end_line else total_lines

                content = "".join(lines[start:end])

        return content, encoding
    except Exception as e:
        logger.error(f"Failed to read file: {file_path}, error: {str(e)}")
        return "", encoding


def read_file(file_path: str) -> str:
    """
    Convenience wrapper to read file content as string.
    """
    content, _ = read_file_content(file_path)
    return content


def write_file_contents(content: str, file_path: str) -> bool:
    """Safe write content to file, creating dirs if needed."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"Failed to write file {file_path}: {e}")
        raise ValueError(f"Failed to write file: {e}")


def write_file(file_path: str, content: str) -> bool:
    """
    Convenience alias for write_file_contents.
    """
    return write_file_contents(content, file_path)


# ============================================================================
# File System Info & Checks
# ============================================================================


def get_directory_size(path: str) -> int:
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size


def is_binary_file(file_path: str) -> bool:
    """Check if file is binary based on extension and content sampling."""
    binary_extensions = {
        ".pyc",
        ".so",
        ".dll",
        ".exe",
        ".bin",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".ico",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".rar",
        ".7z",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
        ".class",
        ".jar",
        ".war",
        ".ear",
        ".o",
        ".a",
        ".lib",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".flv",
        ".wmv",
        ".wma",
        ".ttf",
        ".db",
        ".DS_Store",
    }

    ext = os.path.splitext(file_path)[1].lower()
    if ext in binary_extensions:
        return True

    try:
        with open(file_path, "rb") as f:
            chunk = f.read(4096)

        if b"\x00" in chunk:
            return True

        # Try utf-8
        try:
            chunk.decode("utf-8")
        except UnicodeDecodeError:
            # Check ratio of non-printable
            non_ascii_chars = sum(1 for b in chunk if b < 32 and b != 9 and b != 10 and b != 13)
            # If >30% non-ascii/control, assume binary
            if len(chunk) > 0 and non_ascii_chars / len(chunk) > 0.3:
                return True
            # Otherwise, maybe just bad encoding but text?
            # Standard "is binary" usually implies "not text safe".
            # If decode failed, it's risky.
            return True

        return False

    except OSError:
        return True  # Safer to assume binary if unreadable


def is_text_file(file_path: str) -> bool:
    """Opposite of is_binary, with explicit whitelist checks."""
    file_ext = os.path.splitext(file_path)[1].lower()

    if file_ext in BLACKLIST_FILE_EXTENSIONS:
        return False

    if file_ext in WHITELIST_FILE_EXTENSIONS:
        return True

    return not is_binary_file(file_path)


def is_test_file(file_path: str) -> bool:
    """
    Check if the file is a test file based on common conventions.
    """
    filename = os.path.basename(file_path)

    # Common test patterns
    if filename.startswith("test_") or filename.endswith("_test.py"):  # Python
        return True
    if filename.endswith((".test.js", ".spec.js", ".test.ts", ".spec.ts")):  # JS/TS
        return True
    if filename.endswith("_test.go"):  # Go
        return True
    if filename.endswith("Test.java") or filename.startswith("Test"):  # Java
        return True

    # Check for tests directory
    # Normalize path separators
    normalized_path = file_path.replace("\\", "/")
    if "/tests/" in normalized_path or normalized_path.startswith("tests/"):
        return True

    return False


def filter_code_files(
    all_files: list[str],
    excluded_dirs: list[str] = None,
    excluded_files: list[str] = None,
    include_extensions: list[str] = None,
) -> list[str]:
    """Filter list of files to keep only relevant code files."""
    excluded_dirs = excluded_dirs or DEFAULT_EXCLUDED_DIRS
    excluded_files = excluded_files or DEFAULT_EXCLUDED_FILES

    code_files = []

    for file_path in all_files:
        # Check excluded dirs
        if any(f"/{excluded_dir}/" in f"/{file_path}/" for excluded_dir in excluded_dirs):
            continue

        # Check excluded files
        if any(file_path.endswith(excluded_file) for excluded_file in excluded_files):
            continue

        ext = os.path.splitext(file_path)[1].lower()

        # Check explicit include extensions
        if include_extensions:
            if ext and ext[1:] in include_extensions:
                code_files.append(file_path)
                continue

        # Default check known code extensions
        if ext in CODE_EXTENSION_MAP:
            code_files.append(file_path)

    return code_files


def find_similar_file(file_path: str, repo_files: list[str], threshold: float = 0.7) -> str | None:
    """Fuzzy search for file in list."""
    if not process:
        # Fallback
        for repo_file in repo_files:
            if file_path.lower() in repo_file.lower():
                return repo_file
        return None

    # Full path match
    matches = process.extractOne(file_path, repo_files, scorer=fuzz.WRatio)
    if matches and matches[1] >= threshold * 100:
        return matches[0]

    # Filename match
    filename = os.path.basename(file_path)
    if filename != file_path:
        all_filenames = [os.path.basename(f) for f in repo_files]
        filename_to_path = {os.path.basename(f): f for f in repo_files}

        matches = process.extractOne(filename, all_filenames, scorer=fuzz.WRatio)
        if matches and matches[1] >= threshold * 100:
            return filename_to_path[matches[0]]

    return None
