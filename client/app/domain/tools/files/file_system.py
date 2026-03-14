from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool

from .actions.filesystem import handle_filesystem


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=["path", "destination"],
    summary_template="database_logger.tool_summary.operate_file",
    result_summary_template="database_logger.tool_summary.file_op_result"
)
async def file_system(
    action: Literal["mkdir", "delete", "move"],
    path: str,
    destination: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Perform file system operations: create directory, delete file/directory, or move.

    Args:
        action: Operation to perform ('mkdir', 'delete', 'move').
        path: Target file or directory path.
        destination: Required for 'move' action - the destination path.
    """
    # Map short action names to handler-expected names
    action_map = {"mkdir": "create_directory", "delete": "delete", "move": "move"}
    mapped_action = action_map.get(action, action)
    return await handle_filesystem(mapped_action, path, destination, config)
