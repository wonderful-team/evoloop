from langchain_core.tools import tool
from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator
import os


@tool
async def get_annotated_tree(path: str = ".") -> str:
    """
    Get a directory tree annotated with indexed classes and functions.
    Shows structure + key symbols.
    """
    try:
        target_path = os.path.abspath(path)
        if not os.path.exists(target_path):
             return f"Error: Path {path} not found."
             
        generator = AnnotatedTreeGenerator(target_path)
        return await generator.generate()
    except Exception as e:
        return f"Error generating tree: {e}"
