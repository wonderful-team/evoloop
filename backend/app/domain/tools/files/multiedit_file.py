"""
Multi-edit tool for making multiple edits to a single file in one atomic operation.

This tool is now a thin wrapper around edit_file with the `edits` parameter.
Prefer using edit_file directly with the `edits` argument.
"""

from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool
from .edit_file import handle_multi_edit, FileEditOperation


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=["path"],
    summary_template="database_logger.tool_summary.multiedit_file",
    result_summary_template="database_logger.tool_summary.file_op_result"
)
async def multiedit_file(
    path: str | None = None,
    edits: list[FileEditOperation] | None = None,
    expected_hash: str | None = None,
    verify_types: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Make multiple edits to a single file in one atomic operation.

    This is a convenience wrapper around edit_file(path=..., edits=[...]).
    All behavior, validation, and atomicity guarantees are identical to edit_file.

    Before using this tool:
    1. Use Read tool to understand the file's contents and context
    2. Verify the directory path is correct

    IMPORTANT:
    - All edits are applied in sequence, in the order they are provided
    - Each edit operates on the result of the previous edit
    - All edits must be valid for the operation to succeed - if any edit fails, NONE will be applied
    - This tool is ideal when you need to make several changes to different parts of the same file

    CRITICAL REQUIREMENTS:
    1. All edits follow the same requirements as the single Edit tool
    2. The edits are atomic - either all succeed or none are applied
    3. Plan your edits carefully to avoid conflicts between sequential operations

    WARNING:
    - The tool will fail if an edit's target doesn't match the file contents
    - Since edits are applied in sequence, ensure that earlier edits don't affect the text that later edits are trying to find
    - Always use absolute file paths (starting with /)

    When making edits:
    - Ensure all edits result in idiomatic, correct code
    - Do not leave the code in a broken state
    - Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.

    If you want to create a new file, use:
    - A new file path, including dir name if needed
    - First edit: empty target and the new file's contents as replacement
    - Subsequent edits: normal edit operations on the created content

    Args:
        path: Target file path. **REQUIRED**
        edits: Array of edit operations to perform sequentially. Each edit contains:
               - target: The text to replace (must match file contents)
               - replacement: The new content
               - allow_multiple: Replace all occurrences of target (optional, default false)
               **REQUIRED**
        expected_hash: Expected content hash for concurrent modification detection.
                      Get this from read_file output to ensure you're editing the latest version.
        verify_types: If True (default), perform a semantic type check after all edits.
                      Requires an active LSP for the language.

    Examples:
        # Multiple edits to the same file
        multiedit_file(
            path="src/app.py",
            edits=[
                {"target": "def foo():", "replacement": "def bar():"},
                {"target": "x = 1", "replacement": "x = 2"},
                {"target": "print('hello')", "replacement": "logger.info('hello')"}
            ]
        )
    """
    # Normalize edits to FileEditOperation models
    edit_models = []
    if edits:
        for i, e in enumerate(edits):
            if isinstance(e, FileEditOperation):
                edit_models.append(e)
            elif isinstance(e, dict):
                edit_models.append(FileEditOperation.model_validate(e))
            else:
                return f"Edit #{i+1} is not a valid edit operation. Each edit must be a dict or FileEditOperation."

    return await handle_multi_edit(
        path=path,
        edits=edit_models,
        expected_hash=expected_hash,
        verify_types=verify_types,
        config=config,
    )
