from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool

from .actions.edit import handle_edit
from .actions.filesystem import handle_filesystem
from .actions.list import handle_list
from .actions.read import handle_read
from .actions.write import handle_write


@evoloop_tool
async def manage_file(
    action: Literal["read", "create", "update_block", "overwrite", "list", "list_tree", "create_directory", "delete", "move"],
    path: str,
    content: str | None = None,
    target: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    allow_multiple: bool = False,  # Phase 14: Fuzzy Edit
    max_depth: int = 3,
    with_symbols: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Unified File Management Tool.

    **CRITICAL GUIDELINES**:
    - **Do NOT Guess Paths**: If you are unsure if a file exists, use `action='list'` or `action='list_tree'`.
    - **Explore First**: When exploring a new codebase, `list_tree` is the most efficient way to understand structure.
    - **Read Suggestions**: If you get a "File not found" error, carefully read the suggestions.

    Args:
        action: Operation to perform.
        path: Target file path (or source for move).
        content: Content for 'create', 'overwrite', or replacement for 'update_block'. Alternatively, destination path for 'move'.
        target: Target block to replace (for 'update_block').
        start_line/end_line: For 'read' (limit range).
        allow_multiple: For 'update_block' (replace all occurrences).
        max_depth: For 'list_tree' (default 3).
        with_symbols: For 'list_tree' (default False).
            - False: Returns a FLAT LIST of file paths (Copy-Paste friendly).
            - True: Returns an ASCII TREE with class/function symbols.
    """
    if action == "read":
        return await handle_read(path, start_line, end_line, config)

    elif action in ["create", "overwrite"]:
        return await handle_write(action, path, content, config)

    elif action == "update_block":
        return await handle_edit(path, target, content, allow_multiple, config)

    elif action in ["list", "list_tree"]:
        return await handle_list(action, path, max_depth, with_symbols, config)

    elif action in ["create_directory", "delete", "move"]:
        return await handle_filesystem(action, path, content, config)

    return f"Error: Unknown action '{action}'"
