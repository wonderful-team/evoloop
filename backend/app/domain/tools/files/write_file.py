"""
Write File Tool - Thin wrapper over core.file operations.

This module provides the tool interface for writing files.
All heavy lifting is done by app.core.file module.
"""

import os
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.engine.tasks import persist_file_operation_task
from app.core.file import (
    FileStatus,
)
from app.core.file import (
    write_file as core_write_file,
)
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.i18n.service import i18n

from .utils import resolve_and_validate_path


async def handle_write(
    action: str,
    path: str,
    content: str | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Handle file write operation using core.file module."""
    if content is None:
        return i18n.get("domain_tools.files.write_content_required", action=action)

    try:
        target_path = await resolve_and_validate_path(path, config)

        original_content = None
        op_type = "ADD"

        if os.path.exists(target_path):
            if action == "create":
                return (
                    f"Error: File '{path}' already exists. "
                    "This tool can only create NEW files. To modify or append to an existing file, "
                    "use the edit_file tool."
                )
            # If overwrite is True and file exists, read original content for Rewind
            from app.core.file.verification import safe_read_with_hash

            original_content, _, _ = safe_read_with_hash(target_path)
            op_type = "EDIT"

        # Use core.file for the actual write operation
        result = core_write_file(target_path, content)

        if result.status == FileStatus.SUCCESS:
            # Record Rewind operation
            from app.core.context import ContextManager
            from app.core.file.editor.algorithms import generate_unified_diff

            ctx = ContextManager.current()
            if ctx.thread_id:
                try:
                    diff = generate_unified_diff(
                        original=original_content or "",
                        modified=content,
                        file_path=path,
                    )
                    persist_file_operation_task.delay(
                        thread_id=ctx.thread_id,
                        message_id="",
                        file_path=str(target_path),
                        operation=op_type,
                        diff_content=diff,
                        original_content=original_content,
                        run_id=ctx.run_id,
                        tool_call_id=ctx.current_tool_call_id,
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to persist file operation: {e}")
            
            return i18n.get("domain_tools.files.write_success", path=path)
        elif result.status == FileStatus.PERMISSION_DENIED:
            return i18n.get("domain_tools.files.write_error", error=result.error_message)
        else:
            return i18n.get("domain_tools.files.write_error", error=result.error_message)

    except Exception as e:
        return i18n.get("domain_tools.files.write_error", error=str(e))


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=["path"],
    summary_template="evoloop.tool_summary.write_file",
)
async def write_file(
    path: str,
    content: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Create a new file.

    For targeted modifications to existing files or to overwrite an existing file,
    use the edit_file tool instead, as it preserves unchanged content and has better error recovery.

    Args:
        path: Target file path. **REQUIRED**
        content: The actual file content to write. **REQUIRED**
                 Must contain ONLY the real file text. Do NOT include metadata
                 headers (e.g. [File: ... | Lines ... | Hash: ...]) from
                 read_file output.

    Examples:
        write_file(path="src/main.py", content="print('hello')")  # Create new
    """
    if not path or content is None:
        return (
            "SYSTEM ERROR: You called 'write_file' with EMPTY arguments. "
            "You MUST provide 'path' AND 'content'.\n"
            "CORRECT USAGE: write_file(path='path/to/file.ext', content='file content')\n"
            "ACTION: Retry the tool call immediately with correct arguments."
        )

    # Note: handle_write needs standard args. We rely on global config resolution.
    return await handle_write(
        action="create",
        path=path,
        content=content,
        config=config,
    )
