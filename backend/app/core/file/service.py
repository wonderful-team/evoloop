import logging
import os
from collections.abc import Callable, Iterator

from app.constants import (
    BLACKLIST_FILE_EXTENSIONS,
    DEFAULT_EXCLUDED_DIRS,
    DEFAULT_EXCLUDED_FILES,
    EXTENSION_MAP,
    TEST_FILE_PATTERNS,
    WHITELIST_FILE_EXTENSIONS,
)
from app.utils.file import (
    get_file_ext,
    resolve_path as utils_resolve_path,
)

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz, process
except ImportError:
    process = None


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
    """
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDED_DIRS

    root_path = os.path.abspath(root_path)
    base_depth = root_path.rstrip(os.sep).count(os.sep)

    for root, dirs, files in os.walk(root_path):
        current_depth = root.rstrip(os.sep).count(os.sep) - base_depth

        if max_depth is not None and current_depth >= max_depth:
            dirs[:] = []

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
    Core path resolution with domain-aware logic.
    """
    return utils_resolve_path(file_path, base_path)


def is_binary_file(file_path: str) -> bool:
    """Check if file is binary based on extension and content sampling."""
    ext = get_file_ext(file_path)
    if ext in BLACKLIST_FILE_EXTENSIONS:
        return True

    try:
        with open(file_path, "rb") as f:
            chunk = f.read(4096)

        if b"\x00" in chunk:
            return True

        try:
            chunk.decode("utf-8")
        except UnicodeDecodeError:
            non_ascii_chars = sum(1 for b in chunk if b < 32 and b != 9 and b != 10 and b != 13)
            if len(chunk) > 0 and non_ascii_chars / len(chunk) > 0.3:
                return True
            return True

        return False
    except OSError:
        return True


def is_text_file(file_path: str) -> bool:
    """Opposite of is_binary, with explicit whitelist checks."""
    file_ext = get_file_ext(file_path)
    if file_ext in BLACKLIST_FILE_EXTENSIONS:
        return False
    if file_ext in WHITELIST_FILE_EXTENSIONS:
        return True
    return not is_binary_file(file_path)


def is_test_file(file_path: str) -> bool:
    """Check if file is a test file."""
    filename = os.path.basename(file_path)
    for _lang, patterns in TEST_FILE_PATTERNS.items():
        for pattern in patterns:
            if "." in pattern:
                if filename.endswith(pattern):
                    return True
            else:
                if filename.startswith(pattern):
                    return True
    normalized_path = file_path.replace("\\", "/")
    if "/tests/" in normalized_path or normalized_path.startswith("tests/"):
        return True
    return False


def filter_code_files(
    all_files: list[str],
    excluded_dirs: list[str] | None = None,
    excluded_files: list[str] | None = None,
    include_extensions: list[str] | None = None,
) -> list[str]:
    """Filter list of files to keep only relevant code files."""
    excluded_dirs = excluded_dirs or DEFAULT_EXCLUDED_DIRS
    excluded_files = excluded_files or DEFAULT_EXCLUDED_FILES

    code_files = []
    for file_path in all_files:
        if any(f"/{excluded_dir}/" in f"/{file_path}/" for excluded_dir in excluded_dirs):
            continue
        if any(file_path.endswith(excluded_file) for excluded_file in excluded_files):
            continue
        ext = get_file_ext(file_path)
        if include_extensions:
            if ext and ext[1:] in include_extensions:
                code_files.append(file_path)
                continue
        if ext in EXTENSION_MAP:
            code_files.append(file_path)
    return code_files


def find_similar_file(file_path: str, repo_files: list[str], threshold: float = 0.7) -> str | None:
    """Fuzzy search for file in list."""
    if not process:
        for repo_file in repo_files:
            if file_path.lower() in repo_file.lower():
                return repo_file
        return None

    matches = process.extractOne(file_path, repo_files, scorer=fuzz.WRatio)
    if matches and matches[1] >= threshold * 100:
        return matches[0]

    filename = os.path.basename(file_path)
    if filename != file_path:
        all_filenames = [os.path.basename(f) for f in repo_files]
        filename_to_path = {os.path.basename(f): f for f in repo_files}
        matches = process.extractOne(filename, all_filenames, scorer=fuzz.WRatio)
        if matches and matches[1] >= threshold * 100:
            return filename_to_path[matches[0]]
    return None
