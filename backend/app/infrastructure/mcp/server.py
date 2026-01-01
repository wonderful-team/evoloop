import asyncio
import os

import httpx
from mcp.server.fastmcp import FastMCP
from app.utils import json as json_utils
from app.utils import http as http_utils


from app.core.config import settings
# from app.logging import logger # Uses structlog or logging conf. app.core.config might have settings.

# Import existing domain tools
from app.domain.codebase.indexing.tools import index_path
from app.domain.memory.service import memory_service

# Expose Facades via MCP
from app.domain.tools.facades import manage_file, explore_codebase, manage_git, manage_memory, manage_file

# Initialize FastMCP Server
mcp = FastMCP("EvoLoop MCP Server")


def _truncate(text: str, max_chars: int = 20000) -> str:
    """Safely truncate text to avoid blowing up context window."""
    if not isinstance(text, str):
        return str(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [Truncated. Total length: {len(text)} chars. Use specific tools to read more.]"


@mcp.tool()
def manage_file_ops(
    action: str, 
    path: str, 
    content: str = None, 
    target: str = None, 
    start_line: int = None, 
    end_line: int = None
) -> str:
    """
    Unified File Management. 
    Actions: 'read', 'create', 'update_block', 'overwrite', 'list'.
    """
    try:
        # Map args. invoke expects dict.
        return _truncate(manage_file.invoke({
            "action": action,
            "path": path,
            "content": content,
            "target": target,
            "start_line": start_line,
            "end_line": end_line
        }))
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
async def run_command_ops(command: str) -> str:
    """Run shell command."""
    try:
        from app.domain.tools.execution import run_command
        return _truncate(await run_command.ainvoke({"command": command}))
    except Exception as e:
        return f"Error: {e}"



@mcp.tool()
def read_document(path: str) -> str:
    """Read content from PDF or DOCX file."""
    try:
        from app.domain.tools.document_reader import read_document as read_doc_tool
        return _truncate(read_doc_tool.invoke({"file_path": path}))
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
        from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator

        target_path = os.path.abspath(path)
        if not os.path.exists(target_path):
             return f"Error: Path {path} not found."
             
        generator = AnnotatedTreeGenerator(target_path)
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
        await memory_service.initialize_schema()
        
        # Assume default user "user_default" for now
        await memory_service.add_user_preference("user_default", key, value, description)
        return f"Stored preference: {key}={value}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def remember_concept(name: str, description: str, related_files: list[str] = []) -> str:
    """
    Store a high-level project concept.
    Example: name="Auth Flow", description="Uses JWT with 15min expiry", related_files=["auth.py"]
    """
    try:
        await memory_service.initialize_schema()
        await memory_service.add_concept(name, description, related_files)
        return f"Stored concept: {name}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def query_memory(query: str) -> str:
    """
    Search project memory (Concepts and Preferences).
    """
    try:
        await memory_service.initialize_schema()
        
        prefs = await memory_service.get_user_preferences("user_default")
        concepts = await memory_service.search_concepts(query)
        
        return f"{prefs}\n\n**Relevant Concepts:**\n{concepts}"
    except Exception as e:
        return f"Error: {e}"
