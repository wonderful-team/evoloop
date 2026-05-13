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
from typing import Iterator, List, Optional
from urllib.parse import urlparse

from .types import (
    is_text as is_text_file,
    is_binary as is_binary_file,
    is_test as is_test_file,
    is_image as is_image_file,
    is_video as is_video_file,
    is_audio as is_audio_file,
    is_archive as is_archive_file,
    is_document as is_document_file,
    is_code as is_code_file,
    get_extension as get_file_ext,
    guess_mime as guess_mime_type,
    get_category as get_file_category,
)
from .traverser import FileTraverser, TraverseOptions

logger = logging.getLogger(__name__)


def walk_tree(
    root_path: str,
    exclude_dirs: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_dirs: bool = False
) -> Iterator[str]:
    """
    Standardized directory walker. Delegated to FileTraverser.
    """
    options = TraverseOptions(
        max_depth=max_depth,
        exclude_dirs=exclude_dirs,
        include_dirs=include_dirs,
        recursive=True
    )
    return FileTraverser.walk(root_path, options)


def resolve_path(file_path: str, base_path: Optional[str] = None) -> Optional[str]:
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
        except Exception as e:
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
    except Exception as e:
        raise ValueError(f"Failed to download remote file: {e}")


def filter_code_files(paths: List[str]) -> List[str]:
    """Filter list of paths to only include text/code files."""
    return [p for p in paths if is_text_file(p)]
