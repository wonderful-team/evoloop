import cgi
import logging
import mimetypes
import os
import re
import shutil
import tempfile
import urllib.request
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ============================================================================
# Path Resolution & Navigation
# ============================================================================


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
        return file_path

    # Handle Relative Paths
    if base_path:
        full_path = os.path.abspath(os.path.join(base_path, file_path))
        if os.path.exists(full_path):
            return full_path

        # Fuzzy overlap check
        repo_parts = base_path.split(os.path.sep)
        file_parts = file_path.split("/")
        if file_parts and repo_parts and file_parts[0] == repo_parts[-1]:
            adjusted_path = os.path.join(base_path, *file_parts[1:])
            if os.path.exists(adjusted_path):
                return adjusted_path

        return full_path

    return os.path.abspath(file_path)


def ensure_local_path(file_path: str) -> str:
    """
    If file_path is a URL, download it to a temporary file and return the temp path.
    """
    if file_path.startswith(("http://", "https://")):
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
    """Check if path contains a hash-like pattern."""
    from pathlib import Path
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
    """Read file content with auto encoding detection and optional line range."""
    encoding = get_file_encoding(file_path)
    try:
        with open(file_path, encoding=encoding) as f:
            if start_line is None and end_line is None:
                content = f.read()
            else:
                lines = f.readlines()
                total_lines = len(lines)
                start = max(0, start_line - 1) if start_line else 0
                end = min(total_lines, end_line) if end_line else total_lines
                content = "".join(lines[start:end])
        return content, encoding
    except Exception as e:
        logger.error(f"Failed to read file: {file_path}, error: {str(e)}")
        return "", encoding


def read_file(file_path: str) -> str:
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
    return write_file_contents(content, file_path)


def get_directory_size(path: str) -> int:
    total_size = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size
