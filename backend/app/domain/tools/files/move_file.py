import logging
import os
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.engine.tasks import persist_file_operation_task
from app.core.file import move_path
from app.core.file.verification import safe_read_with_hash
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg

from .utils import resolve_and_validate_path

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=["source", "destination"],
    summary_template="evoloop.tool_summary.move_file",
)
async def move_file(
    source: str,
    destination: str,
    overwrite: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Move or rename a file or directory.

    Args:
        source: The current path of the file or directory. **REQUIRED**
        destination: The new path of the file or directory. **REQUIRED**
        overwrite: Set to True to allow overwriting an existing destination.
                   If False (default) and destination exists, the operation will fail.

    Examples:
        move_file(source="old_name.py", destination="new_name.py")
        move_file(source="file.txt", destination="folder/file.txt", overwrite=True)
    """
    if not source or not destination:
        return "Error: Missing arguments. Both 'source' and 'destination' are required."

    try:
        source_absolute = await resolve_and_validate_path(source, config)
        dest_absolute = await resolve_and_validate_path(destination, config)

        if not os.path.exists(source_absolute):
            return f"Error: Source path '{source}' does not exist."

        if os.path.exists(dest_absolute) and not overwrite:
            return (
                f"Error: Destination '{destination}' already exists. "
                "To overwrite it, you must pass overwrite=True."
            )

        # Record original contents for Rewind
        content = ""
        is_file = os.path.isfile(source_absolute)

        if is_file:
            try:
                content, _, _ = safe_read_with_hash(source_absolute)
            except Exception:
                pass  # Binary files or unreadable files will just have empty diff

        dest_original = None
        if os.path.exists(dest_absolute) and os.path.isfile(dest_absolute) and overwrite:
            try:
                dest_original, _, _ = safe_read_with_hash(dest_absolute)
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        # Perform the move via the File Center
        result = move_path(source_absolute, dest_absolute)
        if not result.success:
            return f"Error moving file: {result.message}"

        # Record Rewind operation
        if is_file:
            from app.core.context import ContextManager

            ctx = ContextManager.current()
            if ctx.thread_id:
                # Record DELETE for source
                persist_file_operation_task.delay(
                    thread_id=ctx.thread_id,
                    message_id="",
                    file_path=str(source_absolute),
                    operation="DELETE",
                    diff_content="",
                    original_content=content,
                    run_id=ctx.run_id,
                    tool_call_id=ctx.current_tool_call_id,
                )
                # Record ADD for destination
                persist_file_operation_task.delay(
                    thread_id=ctx.thread_id,
                    message_id="",
                    file_path=str(dest_absolute),
                    operation="ADD" if dest_original is None else "EDIT",
                    diff_content=content,  # Simplification: use the content directly as diff for ADD
                    original_content=dest_original,
                    run_id=ctx.run_id,
                    tool_call_id=ctx.current_tool_call_id,
                )
        return f"Successfully moved '{source}' to '{destination}'."
    except Exception as e:
        return f"Error moving file: {e}"
