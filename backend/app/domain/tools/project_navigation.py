from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.core.tools import evoloop_tool
from app.domain.tools.files.actions.utils import resolve_and_validate_path


class ListProjectStructureSchema(BaseModel):
    path: str = Field(None, description="Subdirectory to list. If omitted, lists from the current working directory root.")
    depth: int = Field(3, description="Maximum depth of the directory tree to explore.")
    with_symbols: bool = Field(False, description="Whether to include code symbols (classes/functions) in the tree. Defaults to False for speed and token economy.")


@evoloop_tool
async def list_project_structure(
    path: str = None,
    depth: int = 3,
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
        target_path = resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    from app.domain.project.tree_generator import AnnotatedTreeGenerator

    try:
        generator = AnnotatedTreeGenerator(
            target_path,
            max_depth=depth,
            with_symbols=with_symbols,
            file_limit=50
        )
        structure = await generator.generate()
        return structure
    except Exception as e:
        return f"Failed to list structure: {str(e)}"
