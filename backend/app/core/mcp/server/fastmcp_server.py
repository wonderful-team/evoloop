import os

from mcp.server.fastmcp import FastMCP

# Import tools via MCP
from app.domain.codebase.exploration import (
    analyze_impact,
    ask_codebase,
    find_symbol,
)
from app.domain.codebase.indexing.tools import index_path
from app.domain.codebase.retrieval.tools import search_codebase
from app.domain.tools.execution import execute_command
from app.domain.tools.files import (
    edit_file,
    list_directory,
    manage_directory,
    read_file,
    write_file,
)
from app.domain.tools.files import search_files as search_code
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
async def list_directory_ops(path: str, depth: int = 3, tree: bool = True) -> str:
    """List files in a directory. Use tree=True for annotated tree view."""
    try:
        return _truncate(await list_directory.ainvoke({
            "path": path,
            "depth": depth,
            "tree": tree
        }))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def manage_directory_ops(action: str, path: str, destination: str = None) -> str:
    """Directory operations: mkdir, delete, move."""
    try:
        return await manage_directory.ainvoke({
            "action": action,
            "path": path,
            "destination": destination
        })
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def find_symbol_ops(name: str, file_pattern: str = None) -> str:
    """Find definition of a class or function in the codebase."""
    try:
        return _truncate(await find_symbol.ainvoke({
            "name": name,
            "file_pattern": file_pattern
        }))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def search_code_ops(pattern: str, path: str = None) -> str:
    """Search code with regex pattern."""
    try:
        return _truncate(await search_code.ainvoke({
            "pattern": pattern,
            "path": path
        }))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def ask_codebase_ops(question: str) -> str:
    """Ask a natural language question about the codebase."""
    try:
        return _truncate(await ask_codebase.ainvoke({"question": question}))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def analyze_impact_ops(symbol: str) -> str:
    """Analyze the impact of changing a symbol (find usages/dependants)."""
    try:
        return _truncate(await analyze_impact.ainvoke({"symbol": symbol}))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def execute_command_ops(command: str) -> str:
    """Execute shell command including Git operations."""
    try:
        return _truncate(await execute_command.ainvoke({"command": command}))
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
        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager
        # Unified Facade API
        await manager.save_preference(
            user_id="user_default",
            key=key,
            value=value,
            description=description
        )
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
        from app.core.memory.models import Concept
        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager
        concept = Concept(name=name, description=description, project_id=0, related_files=related_files)
        await manager.store_concept(concept)
        return f"Stored concept: {name}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def query_memory(query: str) -> str:
    """
    Search project memory (Concepts and Preferences).
    """
    try:
        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager
        # Unified Facade API
        prefs = await manager.get_merged_preferences("user_default")
        results = await manager.search_concepts(query, 0)
        formatted_results = "\n".join([f"- **{r.name}**: {r.description}" for r in results]) if results else "No concepts found."
        return f"{prefs}\n\n**Relevant Concepts:**\n{formatted_results}"
    except Exception as e:
        return f"Error: {e}"
