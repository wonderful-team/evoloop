import cgi
import hashlib
import logging
import mimetypes
import os
import re
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Large file threshold (10MB)
LARGE_FILE_THRESHOLD = 10 * 1024 * 1024
# Default page size for pagination
DEFAULT_PAGE_SIZE = 100


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


@dataclass
class FileStats:
    """File statistics for pagination and navigation."""
    path: str
    size: int
    total_lines: int
    encoding: str
    is_large: bool
    content_hash: str  # MD5 hash for change detection


def get_file_stats(file_path: str) -> FileStats:
    """Get file statistics including line count and hash."""
    size = os.path.getsize(file_path)
    encoding = get_file_encoding(file_path)

    # Calculate hash for change detection
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    content_hash = hasher.hexdigest()

    # Count lines efficiently
    total_lines = 0
    with open(file_path, "rb") as f:
        for _ in f:
            total_lines += 1

    return FileStats(
        path=file_path,
        size=size,
        total_lines=total_lines,
        encoding=encoding,
        is_large=size > LARGE_FILE_THRESHOLD,
        content_hash=content_hash
    )


def read_file_streaming(
    file_path: str,
    start_line: int | None = None,
    limit: int | None = None
) -> Iterator[str]:
    """
    Stream file content line by line without loading entire file into memory.

    Args:
        file_path: Path to file
        start_line: 1-indexed starting line (None = from beginning)
        limit: Maximum number of lines to yield (None = all)

    Yields:
        Lines from the file
    """
    encoding = get_file_encoding(file_path)
    current_line = 0
    start_idx = (start_line - 1) if start_line else 0
    end_idx = start_idx + limit if limit else None

    with open(file_path, "r", encoding=encoding) as f:
        for line in f:
            if current_line >= start_idx:
                if end_idx is not None and current_line >= end_idx:
                    break
                yield line
            current_line += 1


def read_file_content(file_path: str, start_line: int | None = None, end_line: int | None = None) -> tuple[str, str]:
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


def read_file_content(
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    limit: int | None = None
) -> tuple[str, str, dict]:
    """
    Read file content with auto encoding detection and optional line range.

    Args:
        file_path: Path to the file
        start_line: 1-indexed starting line (for backward compatibility)
        end_line: 1-indexed ending line (inclusive, for backward compatibility)
        limit: Maximum number of lines to read (new preferred way)

    Returns:
        Tuple of (content, encoding, metadata)
        metadata includes: total_lines, has_more, start_line, end_line, content_hash
    """
    encoding = get_file_encoding(file_path)
    stats = get_file_stats(file_path)

    try:
        # Convert end_line to limit for streaming
        if end_line is not None and start_line is not None:
            limit = end_line - start_line + 1

        # Use streaming for large files or when pagination is requested
        if stats.is_large or limit is not None or start_line is not None:
            lines = list(read_file_streaming(file_path, start_line, limit))
            content = "".join(lines)
            actual_lines = len(lines)
            start_idx = (start_line or 1)
            metadata = {
                "total_lines": stats.total_lines,
                "has_more": stats.total_lines > (start_idx + actual_lines - 1),
                "start_line": start_idx,
                "end_line": start_idx + actual_lines - 1,
                "content_hash": stats.content_hash,
                "file_size": stats.size,
                "is_large": stats.is_large
            }
        else:
            # Small file: read all at once
            with open(file_path, encoding=encoding) as f:
                content = f.read()
            metadata = {
                "total_lines": stats.total_lines,
                "has_more": False,
                "start_line": 1,
                "end_line": stats.total_lines,
                "content_hash": stats.content_hash,
                "file_size": stats.size,
                "is_large": False
            }

        return content, encoding, metadata
    except Exception as e:
        logger.error(f"Failed to read file: {file_path}, error: {str(e)}")
        return "", encoding, {"error": str(e)}


def read_file(file_path: str) -> str:
    content, _, _ = read_file_content(file_path)
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


# ============================================================================
# File Outline / Navigation (for large files)
# ============================================================================


def get_file_outline(file_path: str, max_entries: int = 100) -> list[dict]:
    """
    Extract structural outline from code files.
    Uses TreeSitter to support multiple languages (Python, Go, Java, JS, TS, etc.)

    Returns list of outline entries with line numbers.
    """
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    outline = []

    try:
        # Import TreeSitter components from codebase indexing module
        import tree_sitter
        from app.domain.codebase.indexing.parsers import parser_registry
        from app.domain.codebase.indexing.queries import TREE_SITTER_QUERIES

        # Get parser for this file extension
        parser_info = parser_registry.get_parser(ext)
        if not parser_info:
            # No parser available for this extension
            return outline

        parser, language = parser_info

        # Read file content
        with open(file_path, "r", encoding=get_file_encoding(file_path)) as f:
            source = f.read()

        # Parse the file
        tree = parser.parse(bytes(source, "utf8"))
        root_node = tree.root_node

        # Get language key for queries
        lang_key = parser_registry.get_language_key(ext)
        if not lang_key or lang_key not in TREE_SITTER_QUERIES:
            return outline

        # Query for definitions
        query_def = TREE_SITTER_QUERIES[lang_key].get("defs", "")
        if not query_def:
            return outline

        # Execute query using QueryCursor (correct TreeSitter API)
        query = language.query(query_def)
        cursor = tree_sitter.QueryCursor(query)
        matches = list(cursor.matches(root_node))

        # Process matches to extract outline
        lines = source.split("\n")
        processed_ranges = set()

        for _pattern_idx, captured_nodes in matches:
            for capture_name, nodes in captured_nodes.items():
                if capture_name not in ("class", "function"):
                    continue

                # Ensure nodes is a list
                if not isinstance(nodes, list):
                    nodes = [nodes]

                for node in nodes:
                    # Avoid duplicates
                    node_range = (node.start_byte, node.end_byte)
                    if node_range in processed_ranges:
                        continue
                    processed_ranges.add(node_range)

                    # Extract name from captured nodes
                    name = "anonymous"
                    name_nodes = captured_nodes.get("name", [])
                    if name_nodes:
                        if not isinstance(name_nodes, list):
                            name_nodes = [name_nodes]
                        if name_nodes:
                            name = name_nodes[0].text.decode("utf8") if isinstance(name_nodes[0].text, bytes) else name_nodes[0].text

                    line_num = node.start_point[0] + 1  # Convert to 1-based line number
                    line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                    indent = len(line_content) - len(line_content.lstrip())

                    outline.append({
                        "type": "class" if capture_name == "class" else "function",
                        "name": name,
                        "line": line_num,
                        "indent": indent
                    })

                    if len(outline) >= max_entries:
                        break

            if len(outline) >= max_entries:
                break

        # Sort by line number
        outline.sort(key=lambda x: x["line"])

    except ImportError:
        # TreeSitter not available, fall back to Python AST for .py files
        if ext == "py":
            return _get_python_outline_ast(file_path, max_entries)
    except SyntaxError:
        # File has syntax errors, can't parse
        pass
    except Exception as e:
        logger.warning(f"Failed to extract outline from {file_path}: {e}")

    return outline


def _get_python_outline_ast(file_path: str, max_entries: int = 100) -> list[dict]:
    """
    Fallback: Extract outline from Python files using AST.
    Used when TreeSitter is not available.
    """
    outline = []

    try:
        import ast

        with open(file_path, "r", encoding=get_file_encoding(file_path)) as f:
            source = f.read()

        tree = ast.parse(source)
        lines = source.split("\n")

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                outline.append({
                    "type": "class",
                    "name": node.name,
                    "line": node.lineno,
                    "indent": len(lines[node.lineno - 1]) - len(lines[node.lineno - 1].lstrip())
                })
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                # Skip nested functions for brevity
                parent = getattr(node, "parent", None)
                if parent is None or not isinstance(parent, ast.FunctionDef):
                    outline.append({
                        "type": "function",
                        "name": node.name,
                        "line": node.lineno,
                        "indent": len(lines[node.lineno - 1]) - len(lines[node.lineno - 1].lstrip())
                    })

            if len(outline) >= max_entries:
                break

        outline.sort(key=lambda x: x["line"])

    except Exception:
        pass

    return outline


def get_large_file_preview(file_path: str, context_lines: int = 5) -> dict:
    """
    Get a preview of a large file with structural outline and sample content.

    Returns:
        Dictionary with file stats, outline, and preview content
    """
    stats = get_file_stats(file_path)
    outline = get_file_outline(file_path)

    # Get preview: first page + around outline entries
    preview_lines = []
    preview_line_numbers = set(range(1, min(context_lines + 1, stats.total_lines + 1)))

    # Add context around outline entries
    for entry in outline[:20]:  # Top 20 outline items
        line = entry["line"]
        preview_line_numbers.update(range(
            max(1, line - context_lines),
            min(stats.total_lines + 1, line + context_lines + 1)
        ))

    # Sort and limit preview lines
    sorted_lines = sorted(preview_line_numbers)
    if len(sorted_lines) > 100:
        # Too fragmented, just take first 100 lines
        sorted_lines = list(range(1, 101))

    # Read selected lines
    content_parts = []
    current_group = []
    last_line = 0

    encoding = get_file_encoding(file_path)
    with open(file_path, "r", encoding=encoding) as f:
        for line_num, line in enumerate(f, 1):
            if line_num in sorted_lines:
                if last_line and line_num > last_line + 1:
                    # Gap detected
                    if current_group:
                        content_parts.append({"lines": current_group, "content": ""})
                        current_group = []
                    content_parts.append({"gap": True, "from": last_line + 1, "to": line_num - 1})
                current_group.append(line_num)
                last_line = line_num
            elif current_group:
                # We've moved past our selected lines
                break

    # Build preview content
    preview_content = ""
    line_iter = iter(sorted_lines)
    current_line = next(line_iter, None)

    with open(file_path, "r", encoding=encoding) as f:
        for line_num, line in enumerate(f, 1):
            if current_line and line_num == current_line:
                preview_content += f"{line_num:4d}: {line}"
                current_line = next(line_iter, None)

    return {
        "stats": {
            "path": stats.path,
            "size": stats.size,
            "total_lines": stats.total_lines,
            "encoding": stats.encoding,
            "content_hash": stats.content_hash
        },
        "outline": outline,
        "preview": preview_content,
        "preview_lines": sorted_lines
    }


# ============================================================================
# Safe Edit with Hash Verification
# ============================================================================


def safe_read_with_hash(file_path: str) -> tuple[str, str, FileStats]:
    """
    Read file and return content with hash for change detection.

    Returns:
        Tuple of (content, encoding, stats)
    """
    stats = get_file_stats(file_path)
    content, encoding, _ = read_file_content(file_path)
    return content, encoding, stats


def verify_file_hash(file_path: str, expected_hash: str) -> bool:
    """Verify file hasn't changed since last read."""
    try:
        current_stats = get_file_stats(file_path)
        return current_stats.content_hash == expected_hash
    except Exception:
        return False


def write_file_with_verification(
    content: str,
    file_path: str,
    expected_hash: str | None = None
) -> dict:
    """
    Write file with optional hash verification for concurrent modification detection.

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
                return {
                    "success": False,
                    "error": "FILE_MODIFIED",
                    "message": "File was modified by another process. Please re-read and try again."
                }

        # Perform write
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

        # Atomic write: write to temp file then rename
        temp_path = file_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Atomic rename
        os.replace(temp_path, file_path)

        # Get new hash
        new_stats = get_file_stats(file_path)

        return {
            "success": True,
            "path": file_path,
            "new_hash": new_stats.content_hash,
            "bytes_written": len(content.encode("utf-8"))
        }

    except Exception as e:
        logger.error(f"Failed to write file {file_path}: {e}")
        # Clean up temp file if exists
        temp_path = file_path + ".tmp"
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return {
            "success": False,
            "error": "WRITE_FAILED",
            "message": str(e)
        }


def apply_edit_with_verification(
    file_path: str,
    old_string: str,
    new_string: str,
    expected_hash: str | None = None,
    allow_multiple: bool = False
) -> dict:
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
    # Read current content
    content, encoding, metadata = read_file_content(file_path)

    if not content:
        return {
            "success": False,
            "error": "READ_FAILED",
            "message": f"Could not read file: {file_path}"
        }

    # Verify hash if provided
    if expected_hash and metadata.get("content_hash") != expected_hash:
        return {
            "success": False,
            "error": "HASH_MISMATCH",
            "message": "File was modified by another process since last read.",
            "current_hash": metadata.get("content_hash"),
            "expected_hash": expected_hash
        }

    # Check if old_string exists
    if old_string not in content:
        return {
            "success": False,
            "error": "STRING_NOT_FOUND",
            "message": f"Could not find the specified text in file."
        }

    # Count occurrences
    count = content.count(old_string)
    if count > 1 and not allow_multiple:
        return {
            "success": False,
            "error": "MULTIPLE_OCCURRENCES",
            "message": f"Found {count} occurrences. Set allow_multiple=True to replace all.",
            "count": count
        }

    # Apply replacement
    if allow_multiple:
        new_content = content.replace(old_string, new_string)
        replaced_count = count
    else:
        new_content = content.replace(old_string, new_string, 1)
        replaced_count = 1

    # Write with verification
    result = write_file_with_verification(new_content, file_path)

    if result["success"]:
        result["replaced_count"] = replaced_count
        result["old_hash"] = metadata.get("content_hash")

    return result


def get_directory_size(path: str) -> int:
    total_size = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size
