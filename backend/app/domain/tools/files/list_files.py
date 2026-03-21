from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool

from .actions.list import handle_list


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.list_files",
    affected_path_keys=["path"],
    result_summary_template="evoloop_logger.list_summary",
    name_map={"zh": "列出文件", "en": "List Files"}
)
async def list_files(
    path: str,
    depth: int = 3,
    tree: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    List files and subdirectories in a directory.

    Args:
        path: Directory path to explore.
        depth: Maximum depth for tree view (default 3).
        tree: If True, returns annotated directory tree. If False, returns flat file list.
    """
    action: Literal["list", "list_tree"] = "list_tree" if tree else "list"
    return await handle_list(action, path, depth, tree, config)
