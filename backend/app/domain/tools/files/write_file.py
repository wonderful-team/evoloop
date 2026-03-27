from typing import Annotated
from langchain_core.tools import InjectedToolArg
from langchain_core.runnables import RunnableConfig

from app.core.tools import evoloop_tool
from app.i18n.service import i18n
from app.utils.file import write_file_contents as utils_write_file

from .utils import resolve_and_validate_path


async def handle_write(
    action: str,
    path: str,
    content: str | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Handle file write operation."""
    if content is None:
        return i18n.get("domain_tools.files.write_content_required", action=action)

    try:
        target_path = await resolve_and_validate_path(path, config)
        utils_write_file(content, target_path)
        return i18n.get("domain_tools.files.write_success", path=path)
    except Exception as e:
        return i18n.get("domain_tools.files.write_error", error=str(e))


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=["path"],
    summary_template="database_logger.tool_summary.write_file",
    result_summary_template="database_logger.tool_summary.file_op_result",
    name_map={"zh": "写入文件", "en": "Write File"}
)
async def write_file(
    path: str | None = None,
    content: str | None = None,
    overwrite: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Create a new file or overwrite an existing file.

    Args:
        path: Target file path. **REQUIRED**
        content: Content to write. **REQUIRED**
        overwrite: If True, replaces existing file. If False, fails if file exists.

    Example:
        write_file(path="src/main.py", content="print('hello')", overwrite=False)
    """
    # HYPER-ROBUST VALIDATION
    # Zhipu model occasionally sends empty args internally.
    # We catch this and return a prompt-injection style error to force correction.
    if not path or content is None:
        return (
            "SYSTEM ERROR: You called 'write_file' with EMPTY arguments. "
            "You MUST provide 'path' AND 'content'.\n"
            "CORRECT USAGE: write_file(path='path/to/file.ext', content='file content', overwrite=True)\n"
            "ACTION: Retry the tool call immediately with correct arguments."
        )

    # Note: handle_write needs standard args. We rely on global config resolution.
    return await handle_write(
        action="overwrite" if overwrite else "create",
        path=path,
        content=content,
        config=config,
    )
