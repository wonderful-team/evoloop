from typing import Any

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.core.tools import evoloop_tool
from app.domain.tools.files.actions.utils import resolve_and_validate_path


class GetWorkspaceTreeSchema(BaseModel):
    dir_path: str = Field(".", description="Subdirectory to list. If omitted, lists from the current working directory root.")
    max_depth: int = Field(2, description="Maximum depth of the directory tree to explore.")
    with_symbols: bool = Field(False, description="Whether to include code symbols (classes/functions) in the tree. Defaults to False for speed and token economy.")


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "获取工作区树", "en": "Get Workspace Tree"}
)
async def get_workspace_tree(
    dir_path: str = ".",
    max_depth: int = 2,
    with_symbols: bool = False,
    config: RunnableConfig | None = None,
) -> str:
    """
    Explore the codebase structure. Use this to find where files are located or to understand the project layout.
    Returns an annotated ASCII directory tree.
    """
    # 1. Resolve Path
    # We don't have thread_id here directly in the tool call args usually,
    # but tools are run within a context where we can get the current directory.
    # For now, we use a simple detection or rely on absolute paths.

    try:
        target_path = await resolve_and_validate_path(dir_path, config)
    except ValueError as e:
        return str(e)

    from app.domain.project.tree_generator import AnnotatedTreeGenerator

    try:
        generator = AnnotatedTreeGenerator(
            target_path,
            max_depth=max_depth,
            with_symbols=with_symbols,
            file_limit=50
        )
        structure = await generator.generate()
        return structure
    except Exception as e:
        return f"Failed to list structure: {str(e)}"


@evoloop_tool(
    is_state_mutating=True,
    name_map={"zh": "暂存到剪贴板", "en": "Stash to Clipboard"}
)
async def stash_to_clipboard(content: Any, mime_type: str = "text/plain", metadata: dict = None) -> str:
    """
    Stash information (text, image path, UI element bounds) into the agent's short-term workspace clipboard.
    Use this to 'copy' data from one app or step and 'paste' it in another.

    Args:
        content: The data to store. Can be a string, a file path, or a dictionary.
        mime_type: The type of content (e.g., "text/plain", "image/png", "application/json").
        metadata: Optional dictionary with extra context (e.g. {"source_app": "Safari", "field": "email"}).

    Returns:
        Status message. The graph will automatically store this in your 'scratchpad'.
    """
    return f"Successfully stashed {mime_type} to workspace clipboard."


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "从剪贴板检索", "en": "Retrieve from Clipboard"}
)
async def retrieve_from_clipboard() -> str:
    """
    Retrieve all items currently in the workspace clipboard.
    
    Returns:
        A list of currently stashed items. Note: You can usually see these directly in your System Prompt.
    """
    # This tool is a fallback; retrieval is primarily via prompt injection.
    return "Please refer to your System Prompt under 'WORKSPACE CLIPBOARD' to see stashed items."
