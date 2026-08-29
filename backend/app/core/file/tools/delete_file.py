import os
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.file import delete_directory
from app.core.file import delete_file as core_delete_file
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg

from .utils import resolve_and_validate_path


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

        is_file = os.path.isfile(absolute_path)

        # Perform deletion via the File Center
        if is_file:
            result = core_delete_file(absolute_path)
        else:
            result = delete_directory(absolute_path, recursive=True)
        if not result.success:
            return f"Error deleting file: {result.message}"

        return f"Successfully deleted '{path}'."
    except Exception as e:
        return f"Error deleting file: {e}"
