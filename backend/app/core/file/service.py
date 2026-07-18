"""
Standardized high-level file services.
Now delegates traversal and core logic to the File Center (traverser.py).
Provides smart path resolution with URL and fuzzy overlap support.
"""
import cgi
import logging
import mimetypes
import os
import shutil
import tempfile
import urllib.request
from collections.abc import Callable, Iterator
from urllib.parse import urlparse

from .traverser import FileTraverser, TraverseOptions
from .types import (
    is_text as is_text_file,
)

logger = logging.getLogger(__name__)


def walk_tree(
    root_path: str,
    exclude_dirs: list[str] | None = None,
    max_depth: int | None = None,
    include_dirs: bool = False,
    filter_func: Callable[[str], bool] | None = None,
    dir_filter: Callable[[str], bool] | None = None,
    gitignore_root: str | None = None,
) -> Iterator[str]:
    """
    Standardized directory walker. Delegated to FileTraverser.
    """
    options = TraverseOptions(
        max_depth=max_depth,
        exclude_dirs=exclude_dirs,
        include_dirs=include_dirs,
        filter_func=filter_func,
        dir_filter=dir_filter,
        recursive=True,
        gitignore_root=gitignore_root,
    )
    return FileTraverser.walk(root_path, options)


def resolve_path(file_path: str, base_path: str | None = None) -> str | None:
    """
    Smart path resolution.
    Handles:
    - URLs (downloads to local temp)
    - Absolute paths
    - Relative paths (with base_path)
    - Fuzzy overlap (e.g., base=/root/project, file=project/src -> /root/project/src)
    """
    if not file_path:
        return base_path or os.getcwd()

    # 1. Handle URLs
    if file_path.startswith(("http://", "https://")):
        try:
            return ensure_local_path(file_path)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            logger.error(f"Failed to resolve URL {file_path}: {e}")
            return None

    # 2. Expand user
    expanded = os.path.expanduser(file_path)

    # 3. Handle Absolute Paths
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)

    # 4. Handle Relative Paths
    if base_path:
        full_path = os.path.abspath(os.path.join(base_path, expanded))
        if os.path.exists(full_path):
            return full_path

        # Fuzzy overlap check (Heuristic for common Agent path repetition)
        repo_parts = base_path.rstrip(os.path.sep).split(os.path.sep)
        file_parts = expanded.split("/")
        if file_parts and repo_parts and file_parts[0] == repo_parts[-1]:
            adjusted_path = os.path.join(base_path, *file_parts[1:])
            if os.path.exists(adjusted_path):
                return adjusted_path

        return full_path

    return os.path.abspath(expanded)


def ensure_local_path(file_path: str) -> str:
    """
    Downloads remote file to a temporary location if needed.
    """
    if not file_path.startswith(("http://", "https://")):
        return file_path

    try:
        req = urllib.request.Request(file_path, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            parsed = urlparse(file_path)
            ext = os.path.splitext(parsed.path)[1]

            if not ext:
                cd = response.headers.get("Content-Disposition")
                if cd:
                    _, params = cgi.parse_header(cd)
                    if "filename" in params:
                        ext = os.path.splitext(params["filename"])[1]

            if not ext:
                ct = response.headers.get("Content-Type")
                if ct:
                    ext = mimetypes.guess_extension(ct.split(";")[0].strip())

            fd, temp_path = tempfile.mkstemp(suffix=ext or "")
            os.close(fd)

            with open(temp_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)

        logger.info(f"Downloaded {file_path} to {temp_path}")
        return temp_path
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        raise ValueError(f"Failed to download remote file: {e}")


def filter_code_files(paths: list[str]) -> list[str]:
    """Filter list of paths to only include text/code files."""
    return [p for p in paths if is_text_file(p)]
