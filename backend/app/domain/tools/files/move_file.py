import os
import shutil
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.file.verification import safe_read_with_hash
from app.core.tools import evoloop_tool
from app.i18n.service import i18n
from .utils import resolve_and_validate_path
from app.core.engine.tasks import persist_file_operation_task


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
                pass # Binary files or unreadable files will just have empty diff

        dest_original = None
        if os.path.exists(dest_absolute) and os.path.isfile(dest_absolute) and overwrite:
            try:
                dest_original, _, _ = safe_read_with_hash(dest_absolute)
            except Exception:
                pass

        # Perform the move
        # Create parent directories for destination if they don't exist
        os.makedirs(os.path.dirname(dest_absolute), exist_ok=True)
        shutil.move(source_absolute, dest_absolute)

        # Record Rewind operation
        if is_file:
            from app.core.context import ContextManager
            ctx = ContextManager.current()
            if ctx.thread_id:
                try:
                    # Record DELETE for source
                    await persist_file_operation_task(
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
                    await persist_file_operation_task(
                        thread_id=ctx.thread_id,
                        message_id="",
                        file_path=str(dest_absolute),
                        operation="ADD" if dest_original is None else "EDIT",
                        diff_content=content, # Simplification: use the content directly as diff for ADD
                        original_content=dest_original,
                        run_id=ctx.run_id,
                        tool_call_id=ctx.current_tool_call_id,
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to persist file operation for move: {e}")

        return f"Successfully moved '{source}' to '{destination}'."
    except Exception as e:
        return f"Error moving file: {e}"
