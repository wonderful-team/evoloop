from typing import Annotated
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool
from .actions.edit import handle_edit


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=["path"],
    summary_template="database_logger.tool_summary.edit_file",
    result_summary_template="database_logger.tool_summary.file_op_result",
    name_map={"zh": "编辑文件", "en": "Edit File"}
)
async def edit_file(
    path: str | None = None,
    target: str | None = None,
    replacement: str | None = None,
    allow_multiple: bool = False,
    expected_hash: str | None = None,
    dry_run: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Edit a file by replacing a specific block of text.

    Args:
        path: Target file path. **REQUIRED**
        target: The exact text to find. **REQUIRED**
        replacement: The new content. **REQUIRED**
        allow_multiple: If True, replaces ALL occurrences.
        expected_hash: Expected content hash for concurrent modification detection.
                      Get this from read_file output to ensure you're editing the latest version.
        dry_run: If True, preview the change without actually modifying the file.
                 Use this to verify the edit will work as expected.

    Examples:
        # Preview first (recommended for uncertain edits)
        edit_file(path="src/main.py", target="old()", replacement="new()", dry_run=True)
        
        # Then apply
        edit_file(path="src/main.py", target="old()", replacement="new()")
    """
    # HYPER-ROBUST VALIDATION
    if not path or target is None or replacement is None:
        return (
            "SYSTEM ERROR: You called 'edit_file' with EMPTY arguments. "
            "You MUST provide 'path', 'target', and 'replacement'.\n"
            "CORRECT USAGE: edit_file(path='...', target='...', replacement='...')\n"
            "ACTION: Retry the tool call immediately with correct arguments."
        )
    
    # If dry_run, use preview_edit
    if dry_run:
        from .preview_edit import preview_edit_internal
        return await preview_edit_internal(path=path, target=target, replacement=replacement, config=config)

    return await handle_edit(path, target, replacement, allow_multiple, expected_hash, config=config)
