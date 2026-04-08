"""
Read File Tool - Thin wrapper over core.file operations.

This module provides the tool interface for reading files.
All heavy lifting is done by app.core.file module.
"""

import os
import re
from typing import Annotated
from langchain_core.tools import InjectedToolArg
from langchain_core.runnables import RunnableConfig

from app.core.tools import evoloop_tool
from app.core.file import (
    read_file as core_read_file,
    get_file_info,
    get_large_file_preview,
    FileStatus,
    LARGE_FILE_THRESHOLD,
)
from app.domain.tools.document_reader import read_document
from app.i18n.service import i18n

from .utils import resolve_and_validate_path


async def handle_read(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    config: RunnableConfig | None = None,
    include_metadata: bool = True
) -> str:
    """
    Read file content with enhanced metadata and large file support.
    """
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    # Smart routing: if it looks like a doc, use read_document logic
    if path.lower().endswith((".pdf", ".docx", ".doc", ".xlsx", ".xls")):
        return await read_document(
            file_path=target_path,
            start_page=start_line,
            end_page=end_line
        )

    # Check existence
    if not os.path.exists(target_path):
        # Smart Error Handling - suggest similar files
        parent_dir = os.path.dirname(target_path)
        if os.path.exists(parent_dir):
            try:
                siblings = os.listdir(parent_dir)
                siblings_info = []
                for s in siblings[:20]:
                    full_s = os.path.join(parent_dir, s)
                    if os.path.isdir(full_s):
                        siblings_info.append(f"{s}/")
                    else:
                        siblings_info.append(s)
                siblings_str = ", ".join(siblings_info)
                return i18n.get(
                    "domain_tools.files.read_not_found_suggest",
                    path=path,
                    siblings=siblings_str,
                )
            except Exception:
                pass
        return i18n.get("domain_tools.files.read_not_found", path=path)

    # Check if it's a large file (use core.file for size info)
    try:
        file_info = get_file_info(target_path)

        # For large files without pagination, return preview
        if file_info.is_large and start_line is None and end_line is None:
            preview = get_large_file_preview(target_path)
            stats = preview["stats"]
            outline = preview["outline"]

            header = f"""[Large File: {path}]
Size: {stats['size']:,} bytes | Lines: {stats['total_lines']:,} | Hash: {stats['content_hash'][:8]}...

Use `read_file(path='{path}', start_line=N, end_line=M)` to read specific line ranges.
"""
            if outline:
                header += "\nStructure:\n"
                for item in outline[:15]:
                    indent = "  " * (item.get("indent", 0) // 4)
                    header += f"  Line {item['line']:4d}: {indent}{item['type']} {item['name']}\n"
                if len(outline) > 15:
                    header += f"  ... and {len(outline) - 15} more items\n"

            header += f"\n--- Preview (first ~100 lines) ---\n"
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
                lines_read = result.content.count('\n')
                if not result.content.endswith('\n'):
                    lines_read += 1
            else:
                lines_read = 0

            start = start_line or 1
            end = min(start + lines_read - 1, result.metadata.total_lines)

            meta_str = f"""
[File: {path} | Lines {start}-{end} of {result.metadata.total_lines} | Hash: {result.metadata.content_hash}...]
"""
            if end < result.metadata.total_lines:
                meta_str += f"[Use start_line={end + 1} to read more]\n"

            return meta_str + "\n" + result.content

        return result.content

    except Exception as e:
        return i18n.get("domain_tools.files.read_error", error=str(e))


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.read_file",
    affected_path_keys=["path"],
    result_summary_template="database_logger.tool_summary.read_file_result",
    name_map={"zh": "查看文件", "en": "View File"}
)
async def read_file(
    path: str | None = None,
    start_line: str | int | None = None,
    end_line: str | int | None = None,
    include_metadata: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Read the contents of a file.

    Args:
        path: Absolute or relative path to the file. **REQUIRED**
        start_line: Optional start line (1-indexed). Can be int or string.
        end_line: Optional end line (1-indexed, inclusive). Can be int or string.
        include_metadata: Include file stats and hash in output (default: True).
                         Set to False for cleaner output in scripts.
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

    return await handle_read(path, s, e, config=config, include_metadata=include_metadata)
