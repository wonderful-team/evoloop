"""
Directory listing and management tools - Thin wrapper over core.file operations.

This module provides the tool interface for directory operations.
All heavy lifting is done by app.core.file module.
"""

import os
from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool, get_working_directory
from app.core.file import (
    list_directory as core_list_directory,
    create_directory as core_create_directory,
    delete_directory as core_delete_directory,
    delete_file as core_delete_file,
    move_path as core_move_path,
    generate_tree as core_generate_tree,
    resolve_path,
    DirectoryStatus,
)
from app.i18n.service import i18n

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


async def handle_directory_operation(
    action: Literal["mkdir", "delete", "move"],
    path: str,
    destination: str | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Handle directory/file operations using core.file module."""
    root = get_working_directory(config)

    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if action == "mkdir":
        result = core_create_directory(target_path, exist_ok=True)
        if result.success:
            return i18n.get("domain_tools.files.fs_create_dir_success", path=path)
        else:
            return i18n.get("domain_tools.files.fs_create_dir_error", error=result.message)

    elif action == "delete":
        if not os.path.exists(target_path):
            return i18n.get("domain_tools.files.fs_not_found", path=path)
        
        # Determine if it's a file or directory
        if os.path.isdir(target_path):
            result = core_delete_directory(target_path, recursive=True)
            if result.success:
                return i18n.get("domain_tools.files.fs_delete_dir_success", path=path)
            else:
                return i18n.get("domain_tools.files.fs_delete_error", error=result.message)
        else:
            result = core_delete_file(target_path)
            if result.success:
                return i18n.get("domain_tools.files.fs_delete_file_success", path=path)
            else:
                return i18n.get("domain_tools.files.fs_delete_error", error=result.message)

    elif action == "move":
        if not destination:
            return i18n.get("domain_tools.files.fs_move_content_required")

        dest_path = resolve_path(destination, base_path=root)
        if not dest_path:
            return i18n.get("domain_tools.files.fs_move_resolve_error", path=destination)

        # Security Check for Destination
        if not str(dest_path).startswith(str(root)):
            return i18n.get("domain_tools.files.fs_move_security_error", path=destination)

        if not os.path.exists(target_path):
            return i18n.get("domain_tools.files.fs_move_src_not_found", path=path)

        result = core_move_path(target_path, dest_path)
        if result.success:
            return i18n.get("domain_tools.files.fs_move_success", src=path, dest=destination)
        else:
            return i18n.get("domain_tools.files.fs_move_error", error=result.message)

    return i18n.get("domain_tools.files.fs_unknown_action", action=action)


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


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=["path", "destination"],
    summary_template="database_logger.tool_summary.operate_file",
    result_summary_template="database_logger.tool_summary.file_op_result",
    name_map={"zh": "管理目录", "en": "Manage Directory"}
)
async def manage_directory(
    action: Literal["mkdir", "delete", "move"],
    path: str,
    destination: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Manage directories and files: create, delete, or move.

    Args:
        action: Operation to perform. **REQUIRED**
                - "mkdir": Create a new directory
                - "delete": Delete a file or directory
                - "move": Move/rename a file or directory
        path: Target file or directory path. **REQUIRED**
        destination: Required for 'move' action - the destination path.
    
    Examples:
        manage_directory(action="mkdir", path="new_folder/")
        manage_directory(action="delete", path="old_file.txt")
        manage_directory(action="move", path="old_name.txt", destination="new_name.txt")
    """
    return await handle_directory_operation(
        action=action,
        path=path,
        destination=destination,
        config=config
    )
