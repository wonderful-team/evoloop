import os

from langchain_core.runnables import RunnableConfig

from app.domain.tools.document_reader import read_document
from app.i18n.service import i18n
from app.utils.file import (
    read_file_content as utils_read_file,
    get_file_stats,
    get_large_file_preview,
    LARGE_FILE_THRESHOLD
)

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

    Args:
        path: File path
        start_line: 1-indexed starting line
        end_line: 1-indexed ending line (inclusive)
        config: RunnableConfig
        include_metadata: Whether to include file stats in output
    """
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    # Smart routing: if it looks like a doc, use read_document logic
    if path.lower().endswith((".pdf", ".docx", ".doc", ".xlsx", ".xls")):
        return await read_document.ainvoke(
            {"file_path": path, "start_page": start_line, "end_page": end_line},
            config=config
        )

    if not os.path.exists(target_path):
        # Smart Error Handling
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

    try:
        # Check if it's a large file
        file_size = os.path.getsize(target_path)

        # For large files without pagination, return preview
        if file_size > LARGE_FILE_THRESHOLD and start_line is None and end_line is None:
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

        # Normal read with metadata
        file_content, encoding, metadata = utils_read_file(target_path, start_line, end_line)

        if include_metadata:
            meta_str = f"""
[File: {path} | Lines {metadata['start_line']}-{metadata['end_line']} of {metadata['total_lines']} | Hash: {metadata['content_hash'][:8]}...]
"""
            if metadata.get("has_more"):
                meta_str += f"[Use start_line={metadata['end_line'] + 1} to read more]\n"

            return meta_str + "\n" + file_content

        return file_content

    except Exception as e:
        return i18n.get("domain_tools.files.read_error", error=str(e))
