import logging
import os
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.engine.tasks import persist_file_operation_task
from app.core.file import delete_directory
from app.core.file import delete_file as core_delete_file
from app.core.file.verification import safe_read_with_hash
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg

from .utils import resolve_and_validate_path

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=["path"],
    summary_template="evoloop.tool_summary.delete_file",
)
async def delete_file(
    path: str,
    confirm: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Permanently delete a file or directory.
    You MUST pass confirm=True. The deletion can be undone via the Rewind mechanism.

    Args:
        path: Target file or directory path to delete. **REQUIRED**
        confirm: Set to True to confirm the deletion. **REQUIRED**

    Examples:
        delete_file(path="temp.py", confirm=True)
    """
    if not path:
        return "Error: Missing argument 'path'."

    if not confirm:
        return "⚠️ Delete aborted. You must pass confirm=True to proceed with deletion."

    try:
        absolute_path = await resolve_and_validate_path(path, config)

        if not os.path.exists(absolute_path):
            return f"Error: Path '{path}' does not exist."

        # Record original contents for Rewind
        original_content = None
        is_file = os.path.isfile(absolute_path)

        if is_file:
            try:
                original_content, _, _ = safe_read_with_hash(absolute_path)
            except Exception:
                pass  # Binary or unreadable files

        # Perform deletion via the File Center
        if is_file:
            result = core_delete_file(absolute_path)
        else:
            result = delete_directory(absolute_path, recursive=True)
        if not result.success:
            return f"Error deleting file: {result.message}"

        # Record Rewind operation
        if is_file:
            from app.core.context import ContextManager

            ctx = ContextManager.current()
            if ctx.thread_id:
                persist_file_operation_task.delay(
                    thread_id=ctx.thread_id,
                    message_id="",
                    file_path=str(absolute_path),
                    operation="DELETE",
                    diff_content="",
                    original_content=original_content,
                    run_id=ctx.run_id,
                    tool_call_id=ctx.current_tool_call_id,
                )
        return f"Successfully deleted '{path}'."
    except Exception as e:
        return f"Error deleting file: {e}"
