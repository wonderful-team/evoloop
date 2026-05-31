"""
Write File Tool - Thin wrapper over core.file operations.

This module provides the tool interface for writing files.
All heavy lifting is done by app.core.file module.
"""

import os
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.file import (
    write_file as core_write_file,
    FileStatus,
)
from app.core.tools import evoloop_tool
from app.i18n.service import i18n
from .utils import resolve_and_validate_path
from app.core.engine.tasks import persist_file_operation_task


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

        # Check overwrite constraint using RESOLVED path (not raw path)
        # This fixes the bug where os.path.exists(path) checked CWD instead of WORKSPACE_ROOT
        if action == "create" and os.path.exists(target_path):
            return (
                f"Error: File '{path}' already exists. "
                "Use overwrite=True to replace it, or choose a different path."
            )

        # Use core.file for the actual write operation
        result = core_write_file(target_path, content)

        if result.status == FileStatus.SUCCESS:
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
    path: str | None = None,
    content: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Create a new file.

    Args:
        path: Target file path. **REQUIRED**
        content: The actual file content to write. **REQUIRED**
                 Must contain ONLY the real file text. Do NOT include metadata
                 headers (e.g. [File: ... | Lines ... | Hash: ...]) from
                 read_file output.

    Example:
        write_file(path="src/main.py", content="print('hello')")
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
