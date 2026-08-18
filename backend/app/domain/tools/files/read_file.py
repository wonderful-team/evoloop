"""
Read File Tool - Thin wrapper over core.file operations.

This module provides the tool interface for reading files.
All heavy lifting is done by app.core.file module.
"""

import os
import re
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.file import (
    FileStatus,
    get_file_info,
    get_large_file_preview,
)
from app.core.file import (
    read_file as core_read_file,
)
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.i18n.service import i18n

from .utils import resolve_and_validate_path


async def handle_read(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    config: RunnableConfig | None = None,
    include_metadata: bool = True,
) -> str:
    """
    Read file content with enhanced metadata and large file support.
    """
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    # 1. Routing for specialized formats (Documents, Images, Media)
    # These formats have their own internal extraction and formatting.
    special_formats = (
        ".pdf",
        ".docx",
        ".doc",
        ".xlsx",
        ".xls",
        ".png",
        ".jpg",
        ".jpeg",
        ".mp3",
        ".wav",
        ".mp4",
        ".mov",
        ".avi",
        ".html",
    )
    if path.lower().endswith(special_formats):
        try:
            from app.core.file.content_extractor import content_extractor

            return await content_extractor.extract(
                file_path=target_path, start_range=start_line, end_range=end_line
            )
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception(f"Extraction failed for {path}: {e}")
            return i18n.get("domain_tools.files.read_error", error=str(e))

    # 2. Standard Logic for Plain Text / Code
    # This includes existence checks, large file previews, and metadata wrapping.

    # Check existence
    if not os.path.exists(target_path):
        # Smart Error Handling - suggest similar files
        parent_dir = os.path.dirname(target_path)
        if os.path.exists(parent_dir):
            try:
                from app.core.file import FileTraverser

                # Convert iterator to list so we can slice it
                all_entries = list(FileTraverser.list_entries(parent_dir))
                siblings_info = []
                for entry in all_entries[:20]:
                    if entry.is_dir():
                        siblings_info.append(f"{entry.name}/")
                    else:
                        siblings_info.append(entry.name)
                siblings_str = ", ".join(siblings_info)
                return i18n.get(
                    "domain_tools.files.read_not_found_suggest",
                    path=path,
                    siblings=siblings_str,
                )
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)
        return i18n.get("domain_tools.files.read_not_found", path=path)

    # Guard against reading directories
    if os.path.isdir(target_path):
        return (
            f"⚠️ Cannot read a directory with read_file.\n\n"
            f"Path '{path}' is a directory, not a file.\n\n"
            f"Use list_dir(path='{path}') to explore its contents, "
            f"or grep_search(pattern='keyword', path='{path}') to find files inside it."
        )

    # Check if it's a large file (use core.file for size info)
    try:
        file_info = get_file_info(target_path)

        # For large files without pagination, return preview
        if file_info.is_large and start_line is None and end_line is None:
            preview = get_large_file_preview(target_path)
            stats = preview["stats"]
            outline = preview["outline"]

            header = f"""[Large File: {path}]
Size: {stats["size"]:,} bytes | Lines: {stats["total_lines"]:,} | Hash: {stats["content_hash"][:8]}...

Use `read_file(path='{path}', start_line=N, end_line=M)` to read specific line ranges.
"""
            if outline:
                header += "\nStructure:\n"
                for item in outline[:15]:
                    indent = "  " * (item.get("indent", 0) // 4)
                    header += f"  Line {item['line']:4d}: {indent}{item['type']} {item['name']}\n"
                if len(outline) > 15:
                    header += f"  ... and {len(outline) - 15} more items\n"

            header += "\n--- Preview (first ~100 lines) ---\n"
            return header + preview["preview"]

        # Normal read using core.file
        result = core_read_file(target_path, start_line, end_line)

        if result.status == FileStatus.NOT_FOUND:
            return i18n.get("domain_tools.files.read_not_found", path=path)

        if result.status == FileStatus.ENCODING_ERROR:
            return i18n.get("domain_tools.files.read_error", error=result.error_message)

        if result.status == FileStatus.ERROR:
            return i18n.get("domain_tools.files.read_error", error=result.error_message)

        # Format output with metadata
        if include_metadata:
            meta_start = result.metadata.total_lines  # Will be updated below
            meta_end = result.metadata.total_lines

            # Calculate actual line range
            if result.content:
                lines_read = result.content.count("\n")
                if not result.content.endswith("\n"):
                    lines_read += 1
            else:
                lines_read = 0

            start = start_line or 1
            end = min(start + lines_read - 1, result.metadata.total_lines)

            meta_str = f"""[File: {path} | Lines {start}-{end} of {result.metadata.total_lines} | Hash: {result.metadata.content_hash}]
"""
            if end < result.metadata.total_lines:
                meta_str += f"[Use start_line={end + 1} to read more]\n"

            return meta_str + "\n" + result.content, {
                "start_line": start,
                "end_line": end,
                "total_lines": result.metadata.total_lines,
            }

        return result.content, {
            "start_line": start_line or 1,
            "end_line": end_line or 1000,
        }

    except Exception as e:
        return i18n.get("domain_tools.files.read_error", error=str(e))


# Output budget for read_file tool
MAX_LINES_PER_CALL = 1000


@evoloop_tool(
    summary_template="evoloop.tool_summary.read_file",
    affected_path_keys=["path"],
)
async def read_file(
    path: str,
    start_line: str | int | None = None,
    end_line: str | int | None = None,
    include_metadata: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Read the contents of a file.

    ⚡ EFFICIENCY TIP:
       - If you need to read a specific small section, pass start_line and end_line.
       - If you need to inspect many different parts of the same file, it is MUCH MORE EFFICIENT
         to make a SINGLE call reading a large continuous chunk (e.g. 1 to 1000) rather than
         making dozens of small read_file calls for individual functions or line ranges.

    Output Limit: Maximum 1000 lines per call.
    For larger files, make multiple calls to read the next segment (e.g. 1001-2000).

    Important: When include_metadata=True (default), the output starts with a header like:
      [File: path | Lines X-Y of Z | Hash: abc123]
    This header is for display and tracking ONLY. The actual file content begins
    on the line immediately after this header. Do NOT treat the header as part
    of the file when passing content to write_file or edit_file.

    Args:
        path: Absolute or relative path to the file. **REQUIRED**
        start_line: Optional start line (1-indexed). Can be int or string.
        end_line: Optional end line (1-indexed, inclusive). Can be int or string.
        include_metadata: Include file stats and hash in output (default: True).
                         Set to False for cleaner output in scripts.

    Examples:
        read_file(path="main.py")  # First 1000 lines (default)
        read_file(path="main.py", end_line=500)  # First 500 lines
        read_file(path="main.py", start_line=1, end_line=1000)  # Lines 1-1000
        read_file(path="main.py", start_line=1001, end_line=2000)  # Lines 1001-2000
    """
    if not path:
        return "Error: Missing argument 'path'. usage: read_file(path='...')"

    # Helper to safely parse integers from loose model output (e.g. "1 Union College")
    def safe_int(val):
        if val is None:
            return None
        if isinstance(val, int):
            return val
        try:
            # Try simple conversion
            return int(str(val).strip())
        except ValueError:
            # Fallback: Extract first digit sequence if mixed garbage
            match = re.search(r"\d+", str(val))
            if match:
                return int(match.group())
            return None

    s = safe_int(start_line)
    e = safe_int(end_line)

    # Budget check
    effective_start = s if s is not None else 1
    default_end = effective_start + MAX_LINES_PER_CALL - 1

    # If user asked for too much, we truncate and warn
    is_truncated = False
    if e is not None and (e - effective_start + 1) > MAX_LINES_PER_CALL:
        effective_end = default_end
        is_truncated = True
    else:
        effective_end = e if e is not None else default_end

    res = await handle_read(path, effective_start, effective_end, config=config, include_metadata=include_metadata)
    
    if isinstance(res, tuple):
        result_str, meta = res
    else:
        result_str = res
        meta = {"start_line": effective_start, "end_line": effective_end}

    if is_truncated:
        warning = f"\n\n... (Output truncated to {MAX_LINES_PER_CALL} lines)\n"
        warning += f"Tip: The requested range was too large. Use start_line={effective_end + 1} to read the next segment."
        return result_str + warning, meta

    return result_str, meta
