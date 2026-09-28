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
from app.core.file.constants import MAX_LINES_PER_CALL
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
        # Smart Error Handling - suggest similar files (difflib 相似度 top3)
        parent_dir = os.path.dirname(target_path)
        if os.path.exists(parent_dir):
            try:
                from app.core.file import FileTraverser

                # Convert iterator to list so we can slice it
                all_entries = list(FileTraverser.list_entries(parent_dir))
                wanted = os.path.basename(target_path)
                if wanted:
                    import difflib

                    names = [
                        (f"{e.name}/" if e.is_dir() else e.name) for e in all_entries
                    ]
                    similar = difflib.get_close_matches(wanted, names, n=3, cutoff=0.2)
                    if similar:
                        return i18n.get(
                            "domain_tools.files.read_not_found_suggest",
                            path=path,
                            siblings=", ".join(similar),
                        )
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

    # Directory support (§10.2.3: read 吸收 list_dir，目录直接列出条目)
    if os.path.isdir(target_path):
        from app.core.file.tools.list_dir import handle_list

        listing = await handle_list(path=path, config=config)
        if isinstance(listing, tuple):
            text, meta = listing
            return f"<directory listing for {path}>\n" + text, meta
        return listing

    # Binary sniff：检测不可读文本的二进制文件（对齐 OpenCode 50KB sniff）
    try:
        with open(target_path, "rb") as _f:
            _head = _f.read(2048)
        if b"\x00" in _head:
            return (
                f"[Binary file: {path}] 该文件为二进制，无法以文本读取"
                f"（大小 {os.path.getsize(target_path)} bytes）。"
            )
    except OSError as e:
        logger.debug("Suppressed binary sniff error: %s", e, exc_info=True)

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


async def read_file(
    path: str,
    start_line: str | int | None = None,
    end_line: str | int | None = None,
    include_metadata: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    读取本地文件或目录的内容。如果路径不存在，会返回错误。

    ⚡ 效率提示：
       - 只需读某段小内容时，传 start_line 和 end_line。
       - 需要读同一文件多处时，**一次调用读一大段连续内容**（如 1-1000 行）远比
         多次小段调用（按函数/行区间）更高效。

    输出限制：每次调用最多 1000 行。更大的文件请多次调用读下一段（如 1001-2000）。

    重要：当 include_metadata=True（默认）时，输出会带一个头部，如：
      [File: path | Lines X-Y of Z | Hash: abc123]
    该头部仅用于展示与追踪。真正的文件内容从头部下一行开始。**把内容传给
    write_file / edit_file 时不要把头部当作文件内容。**

    Args:
        path: 文件绝对或相对路径。**必填**
        start_line: 可选起始行（从 1 开始）。可以是 int 或 str。
        end_line: 可选结束行（从 1 开始，含）。可以是 int 或 str。
        include_metadata: 输出是否包含文件统计与哈希（默认 True）。脚本中想更干净可设 False。

    Examples:
        read_file(path="main.py")  # 前 1000 行（默认）
        read_file(path="main.py", end_line=500)  # 前 500 行
        read_file(path="main.py", start_line=1, end_line=1000)  # 第 1-1000 行
        read_file(path="main.py", start_line=1001, end_line=2000)  # 第 1001-2000 行
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

    res = await handle_read(
        path,
        effective_start,
        effective_end,
        config=config,
        include_metadata=include_metadata,
    )

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
