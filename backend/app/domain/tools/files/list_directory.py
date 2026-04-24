"""
Directory listing and management tools - Thin wrapper over core.file operations.

This module provides the tool interface for directory operations.
All heavy lifting is done by app.core.file module.
"""

import os
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.file import (
    list_directory as core_list_directory,
    generate_tree as core_generate_tree,
)
from app.core.tools import evoloop_tool
from .utils import resolve_and_validate_path


async def handle_list(
    path: str,
    tree: bool = True,
    max_depth: int = 3,
    with_symbols: bool = False,
    config: RunnableConfig | None = None,
) -> str:
    """Handle file listing operations using core.file module."""
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if not os.path.exists(target_path):
        return f"Error: Path does not exist: {path}"

    if not tree:
        # Simple flat listing using core.file
        entries = list(core_list_directory(target_path, recursive=False))
        lines = [f"{e.name}/" if e.is_dir else e.name for e in entries]
        return '\n'.join(lines[:200])  # Limit output
    else:
        # Tree view using core.file
        # For with_symbols=True, fall back to existing tree generator
        if with_symbols:
            from app.domain.project.tree_generator import AnnotatedTreeGenerator
            try:
                generator = AnnotatedTreeGenerator(
                    target_path,
                    max_depth=max_depth,
                    with_symbols=True,
                    file_limit=50,
                )
                tree_output = await generator.generate()
                return tree_output
            except Exception as e:
                return f"Error generating annotated tree: {e}"
        else:
            # Use core.file tree generation
            return core_generate_tree(target_path, max_depth=max_depth)


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.list_files",
    affected_path_keys=["path"],
    result_summary_template="evoloop_logger.list_summary",
    name_map={"zh": "列出目录", "en": "List Directory"}
)
async def list_directory(
    path: str,
    tree: bool = True,
    depth: int = 3,
    with_symbols: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    List files and subdirectories in a directory.

    Args:
        path: Directory path to explore. **REQUIRED**
        tree: If True, returns directory tree. If False, returns flat file list.
        depth: Maximum depth for tree view (default 3).
        with_symbols: If True, includes class and function names in the tree (requires indexing).
    
    Examples:
        # Get tree view of project structure
        list_directory(path="src/", tree=True)
        
        # Simple flat list
        list_directory(path="src/", tree=False)
    """
    return await handle_list(
        path=path,
        tree=tree,
        max_depth=depth,
        with_symbols=with_symbols,
        config=config
    )
