"""
Write File Tool - Thin wrapper over core.file operations.

This module provides the tool interface for writing files.
All heavy lifting is done by app.core.file module.
"""

import os
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.file import (
    FileStatus,
)
from app.core.file import (
    write_file as core_write_file,
)
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

        if os.path.exists(target_path):
            if action == "create":
                return (
                    f"Error: File '{path}' already exists. "
                    "This tool can only create NEW files. To modify or append to an existing file, "
                    "use the edit_file tool."
                )

        # Use core.file for the actual write operation
        result = core_write_file(target_path, content)

        if result.status == FileStatus.SUCCESS:
            return i18n.get("domain_tools.files.write_success", path=path)
        elif result.status == FileStatus.PERMISSION_DENIED:
            return i18n.get(
                "domain_tools.files.write_error", error=result.error_message
            )
        else:
            return i18n.get(
                "domain_tools.files.write_error", error=result.error_message
            )

    except Exception as e:
        return i18n.get("domain_tools.files.write_error", error=str(e))


async def write_file(
    path: str,
    content: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    创建新文件。

    对已有文件的定向修改或覆盖，请用 edit_file 工具——它能保留未改内容、错误恢复更好。

    Args:
        path: 目标文件路径。**必填**
        content: 要写入的实际文件内容。**必填**
                 只能包含真实的文件文本。**不要包含** read_file 输出的元数据头
                 （如 [File: ... | Lines ... | Hash: ...]）。

    Examples:
        write_file(path="src/main.py", content="print('hello')")  # 新建
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
