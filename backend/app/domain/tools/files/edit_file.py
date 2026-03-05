from typing import Annotated
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool
from .actions.edit import handle_edit


@evoloop_tool(is_state_mutating=True, affected_path_keys=["path"])
async def edit_file(
    path: str | None = None,
    target: str | None = None,
    replacement: str | None = None,
    allow_multiple: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Edit a file by replacing a specific block of text.

    Args:
        path: Target file path. **REQUIRED**
        target: The exact text to find. **REQUIRED**
        replacement: The new content. **REQUIRED**
        allow_multiple: If True, replaces ALL occurrences.

    Example:
        edit_file(path="src/main.py", target="old_function()", replacement="new_function()")
    """
    # HYPER-ROBUST VALIDATION
    if not path or target is None or replacement is None:
        return (
            "SYSTEM ERROR: You called 'edit_file' with EMPTY arguments. "
            "You MUST provide 'path', 'target', and 'replacement'.\n"
            "CORRECT USAGE: edit_file(path='...', target='...', replacement='...')\n"
            "ACTION: Retry the tool call immediately with correct arguments."
        )

    return await handle_edit(path, target, replacement, allow_multiple, config=config)
