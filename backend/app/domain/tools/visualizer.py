import os

from langchain_core.tools import tool

from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator


from app.logging import get_context

@tool
async def get_annotated_tree(path: str = ".", max_depth: int = 3, pattern: str = None) -> str:
    """
    Get a directory tree annotated with indexed classes and functions.
    Shows structure + key symbols.
    
    Args:
        path: Relative or absolute path to the directory (default: root).
        max_depth: Maximum depth to traverse (default: 3). Increase if you need to see deeper structure, but be mindful of context size.
        pattern: Optional Glob pattern to filter files (e.g. "*.py", "*Controller*"). If set, only matching files and their parent directories will be shown.
    """
    try:
        # Resolve path from context if relative
        if not os.path.isabs(path):
            ctx = get_context()
            root = ctx.get("working_directory", os.getcwd())
            path = os.path.join(root, path)

        target_path = os.path.abspath(path)
        if not os.path.exists(target_path):
             return f"Error: Path {path} not found."
             
        # Instantiate with max_depth and pattern
        generator = AnnotatedTreeGenerator(target_path, max_depth=max_depth, pattern=pattern)
        return await generator.generate()
    except Exception as e:
        return f"Error generating tree: {e}"
