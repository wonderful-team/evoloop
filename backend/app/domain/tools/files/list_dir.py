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


def _format_size(size: int) -> str:
    """Format file size in human-readable form."""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}K"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}M"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f}G"


def _get_line_count(file_path: str, max_size: int = 1024 * 1024) -> int | None:
    """Return line count for files under max_size, else None."""
    try:
        size = os.path.getsize(file_path)
        if size == 0 or size > max_size:
            return None
        with open(file_path, "rb") as f:
            if b"\x00" in f.read(4096):
                return None
        with open(file_path, "rb") as f:
            return sum(1 for _ in f)
    except Exception:
        return None


async def handle_list(
    path: str,
    tree: bool = False,
    max_depth: int = 1,
    filter_pattern: str | None = None,
    stats: bool = True,
    with_symbols: bool = False,
    max_entries: int = 200,
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
        entries = list(core_list_directory(target_path, recursive=False, filter_pattern=filter_pattern))
        # In flat mode with filter, only show directories whose names also match the filter
        if filter_pattern:
            import fnmatch
            entries = [e for e in entries if not e.is_dir or fnmatch.fnmatch(e.name, filter_pattern)]
        lines = []
        for e in entries:
            if e.is_dir:
                lines.append(f"{e.name}/")
            else:
                size_str = f"  {_format_size(e.size)}" if stats else ""
                lines_str = ""
                if stats and e.size <= 1024 * 1024:
                    lc = _get_line_count(e.path)
                    if lc is not None:
                        lines_str = f" ({lc} lines)"
                lines.append(f"{e.name}{size_str}{lines_str}")

        output = '\n'.join(lines[:max_entries])

        # 【虚拟注入】在根目录列表中注入 uploads/ 条目
        # 无论全局模式还是项目模式，uploads/ 都指向 CHAT_UPLOAD_DIR (~/.evoloop/uploads/)
        # 让 Agent 在任何模式下都能清楚地"看到"聊天附件的存放位置
        from app.infrastructure.config.service import SystemConfigService
        workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
        is_root_listing = (path in (".", "") or
                          (workspace_root and target_path == workspace_root) or
                          target_path == workspace_root)

        if is_root_listing and not any(l.startswith("uploads/") for l in lines):
            output = "uploads/\n" + output if output else "uploads/"

        if len(lines) > max_entries:
            output += f"\n\n... ({len(lines) - max_entries} more entries hidden)\nTip: Use filter=\"*.ext\" to narrow results, or increase max_entries."
        return output, {"count": len(lines), "recursive": False}
    else:
        # Tree view using core.file
        # For with_symbols=True, fall back to existing tree generator
        if with_symbols:
            from app.core.project.tree_generator import AnnotatedTreeGenerator
            try:
                generator = AnnotatedTreeGenerator(
                    target_path,
                    max_depth=max_depth,
                    with_symbols=True,
                    file_limit=50,
                )
                tree_output = await generator.generate()
                tree_count = len([l for l in tree_output.splitlines() if l.strip()])
                return tree_output, {"count": tree_count, "recursive": True}
            except Exception as e:
                return f"Error generating annotated tree: {e}"
        else:
            # Use core.file tree generation (compact format)
            tree_output = core_generate_tree(
                target_path,
                max_depth=max_depth,
                max_entries=max_entries,
                with_stats=stats,
            )
            tree_count = len([l for l in tree_output.splitlines() if l.strip()])
            return tree_output, {"count": tree_count, "recursive": max_depth > 1}


@evoloop_tool(
    is_pollable=True,
    summary_template="evoloop.tool_summary.list_files",
    affected_path_keys=["path"],
)
async def list_dir(
    path: str,
    tree: bool = False,
    depth: int = 1,
    filter: str | None = None,
    stats: bool = True,
    with_symbols: bool = False,
    max_entries: int = 200,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Browse and explore directory contents with filtering, stats, and tree view.

    Use this tool to:
    - Explore project structure (tree view)
    - Find files by type or name pattern (filter)
    - Analyze directory composition (stats)
    - Navigate the codebase efficiently

    Args:
        path: Directory path to explore. **REQUIRED**
        tree: If True, returns hierarchical tree. If False, returns flat file list.
              Use tree=True to understand nested structure; use tree=False for a quick scan.
        depth: Maximum depth for tree view (default: 1).
               IMPORTANT: depth only works when tree=True.
               When tree=False (flat list), depth is ignored and all entries are shown at the same level.
               Use depth=1 for top-level overview (recommended first step).
               Use depth=2+ only when you need to see nested structure.
        filter: Filename pattern to filter results. Examples:
                - "*.py" → only Python files
                - "test_*" → files starting with "test_"
                - "*.js|*.ts" → JavaScript or TypeScript files
                When filter is set, matching is applied at all depths.
        stats: If True (default), includes file size (flat mode) and directory
               file counts (tree mode). Helps identify important files at a glance.
               Set to False for cleaner output when size info is not needed.
        max_entries: Maximum number of entries to return (default: 200).
                     Increase this (e.g. 500 or 1000) when you need to see more
                     entries in large directories. Be aware that very large values
                     will consume more tokens in the response.
        with_symbols: If True, includes class and function names in the tree
                      (requires indexing, may be slow on large projects).

    Examples:
        # Quick overview of project top-level
        list_dir(path="src/")

        # Find all Python files in a module
        list_dir(path="src/core/", filter="*.py")

        # Deep dive into a specific directory
        list_dir(path="src/core/", tree=True, depth=2)

        # Find test files anywhere in the project
        list_dir(path=".", tree=True, depth=2, filter="test_*.py")
    """
    return await handle_list(
        path=path,
        tree=tree,
        max_depth=depth,
        filter_pattern=filter,
        stats=stats,
        with_symbols=with_symbols,
        max_entries=max_entries,
        config=config
    )
