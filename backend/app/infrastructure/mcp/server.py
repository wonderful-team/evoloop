import os

from mcp.server.fastmcp import FastMCP

# Import existing domain tools
from app.domain.codebase.indexing.tools import index_path
from app.domain.codebase.retrieval.tools import search_codebase
from app.core.memory import memory_manager

# Expose Facades via MCP
from app.domain.tools.facades import (
    explore_codebase,
    manage_git,
    manage_memory,
)

# Phase 18: Import new atomic file tools
from app.domain.tools.files import (
    edit_file,
    file_system,
    list_files,
    read_file,
    write_file,
)
from app.utils import json as json_utils

# Initialize FastMCP Server
mcp = FastMCP("EvoLoop MCP Server")


def _truncate(text: str, max_chars: int = 20000) -> str:
    """Safely truncate text to avoid blowing up context window."""
    if not isinstance(text, str):
        return str(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [Truncated. Total length: {len(text)} chars. Use specific tools to read more.]"


# Phase 18: Atomic File Tools for MCP
@mcp.tool()
async def read_file_ops(path: str, start_line: int = None, end_line: int = None) -> str:
    """Read a file's contents. Optionally specify line range."""
    try:
        return _truncate(await read_file.ainvoke({
            "path": path,
            "start_line": start_line,
            "end_line": end_line
        }))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def write_file_ops(path: str, content: str, overwrite: bool = False) -> str:
    """Create a new file or overwrite an existing file."""
    try:
        return await write_file.ainvoke({
            "path": path,
            "content": content,
            "overwrite": overwrite
        })
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def edit_file_ops(path: str, target: str, replacement: str, allow_multiple: bool = False) -> str:
    """Edit a file by replacing a specific text block."""
    try:
        return await edit_file.ainvoke({
            "path": path,
            "target": target,
            "replacement": replacement,
            "allow_multiple": allow_multiple
        })
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def list_files_ops(path: str, depth: int = 3, tree: bool = True) -> str:
    """List files in a directory. Use tree=True for annotated tree view."""
    try:
        return _truncate(await list_files.ainvoke({
            "path": path,
            "depth": depth,
            "tree": tree
        }))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def file_system_ops(action: str, path: str, destination: str = None) -> str:
    """File system operations: mkdir, delete, move."""
    try:
        return await file_system.ainvoke({
            "action": action,
            "path": path,
            "destination": destination
        })
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def explore_codebase_ops(
    action: str,
    query: str,
    scope_path: str = None
) -> str:
    """
    Unified Codebase Exploration.
    Actions: 'search_symbol', 'search_text', 'search_concept'.
    """
    try:
        return _truncate(await explore_codebase.ainvoke({
            "action": action,
            "query": query,
            "scope_path": scope_path
        }))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def manage_git_ops(action: str, argument: str = None) -> str:
    """Unified Git Operations."""
    try:
        return _truncate(manage_git.invoke({"action": action, "argument": argument}))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def manage_memory_ops(action: str, key: str = None, value: str = None) -> str:
    """Unified Memory Operations."""
    try:
        return await manage_memory.ainvoke({"action": action, "key": key, "value": value})
    except Exception as e:
        return f"Error: {e}"


# Kept independent
@mcp.tool()
async def bash_ops(command: str) -> str:
    """Run shell command."""
    try:
        from app.domain.tools.execution import bash

        return _truncate(await bash.ainvoke({"command": command}))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def read_document(path: str) -> str:
    """Read content from PDF or DOCX file."""
    try:
        from app.domain.tools.document_reader import read_document as read_doc_tool

        return _truncate(await read_doc_tool.ainvoke({"file_path": path}))
    except Exception as e:
        return f"Error reading document: {e}"


@mcp.tool()
async def search_semantic(query: str) -> str:
    """Semantic search in the codebase."""
    try:
        return await search_codebase.ainvoke({"query": query})
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def index_directory(path: str) -> str:
    """Index a directory or file."""
    try:
        return await index_path.ainvoke({"path": path})
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def analyze_code_file(path: str) -> str:
    """
    Deeply analyze a code file (structure, imports, metrics).
    Use this to understand class/function definitions and dependencies.
    """
    try:
        from app.domain.codebase.analysis.code_analyzer import code_analyzer

        result = code_analyzer.analyze_file(path)
        return json_utils.dumps(result, indent=2)
    except Exception as e:
        return f"Error analyzing file: {e}"


@mcp.tool()
async def get_annotated_tree(path: str = ".") -> str:
    """
    Get a directory tree annotated with indexed classes and functions.
    Shows structure + key symbols.
    """
    try:
        from app.domain.project.tree_generator import AnnotatedTreeGenerator

        target_path = os.path.abspath(path)
        if not os.path.exists(target_path):
            return f"Error: Path {path} not found."

        generator = AnnotatedTreeGenerator(target_path, file_limit=30)
        return _truncate(await generator.generate())
    except Exception as e:
        return f"Error generating tree: {e}"


@mcp.tool()
async def remember_preference(key: str, value: str, description: str = "") -> str:
    """
    Store a user preference or project rule.
    Example: key="code_style", value="Use Pydantic v2", description="Strict validation required"
    """
    try:
        # Ensure schema
        await memory_manager.initialize()
        await memory_manager.preferences.set_preference("user_default", key, value, description)
        return f"Stored preference: {key}={value}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def remember_concept(name: str, description: str, related_files: list[str] | None = None) -> str:
    """
    Store a high-level project concept.
    Example: name="Auth Flow", description="Uses JWT with 15min expiry", related_files=["auth.py"]
    """
    if related_files is None:
        related_files = []
    try:
        await memory_manager.initialize()
        from app.core.memory.interfaces.long_term import Concept
        concept = Concept(name, description, 0, related_files)
        await memory_manager.long_term.store_concept(concept)
        return f"Stored concept: {name}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def query_memory(query: str) -> str:
    """
    Search project memory (Concepts and Preferences).
    """
    try:
        await memory_manager.initialize()
        prefs = await memory_manager.preferences.get_merged_preferences("user_default")
        results = await memory_manager.long_term.search_concepts(query, 0)
        formatted_results = "\n".join([f"- **{r.name}**: {r.description}" for r in results]) if results else "No concepts found."
        return f"{prefs}\n\n**Relevant Concepts:**\n{formatted_results}"
    except Exception as e:
        return f"Error: {e}"
