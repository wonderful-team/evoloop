import asyncio
import json
import os

import httpx
from mcp.server.fastmcp import FastMCP


from app.core.config import settings
# from app.logging import logger # Uses structlog or logging conf. app.core.config might have settings.

# Import existing domain tools
from app.infrastructure.filesystem.tool import list_files, read_file, grep_files, write_file_content
from app.domain.tools.execution import run_shell_command
from app.domain.codebase.retrieval.tools import search_codebase
from app.domain.codebase.indexing.tools import index_path
from app.domain.memory.service import memory_service

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
def list_directory(path: str = ".") -> str:
    """List files in a directory."""
    try:
        # Invoke the existing langchain tool
        res = list_files.invoke({"path": path})
        return _truncate(res)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def read_file_content(path: str) -> str:
    """Read content of a file."""
    try:
        return _truncate(read_file.invoke({"path": path}))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_file_stats(path: str) -> str:
    """
    Get file statistics (size, lines) BEFORE reading it.
    Use this to decide a reading strategy for large files.
    """
    if not os.path.exists(path):
        return f"Error: File {path} not found."
        
    try:
        file_size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            line_count = len(lines)
            content_preview = "".join(lines[:5])
            
        # Strategy Logic
        strategy = "✅ Safe to read completely."
        if file_size > 50_000: # 50KB
            strategy = "⚠️ Large file. Suggest reading with `read_file_content` using line ranges if supported, or just read cautiously."
        if file_size > 500_000: # 500KB
             strategy = "⛔ Very large file (0.5MB+). Do NOT read fully. Use `grep_search` or specific line ranges."
             
        return (
            f"File: {path}\n"
            f"Size: {file_size} bytes\n"
            f"Lines: {line_count}\n"
            f"Strategy: {strategy}\n"
            f"Preview:\n{content_preview}"
        )
    except Exception as e:
        return f"Error getting stats: {e}"


@mcp.tool()
def grep_search(pattern: str, path: str = ".") -> str:
    """Search for a pattern in files."""
    try:
        return _truncate(grep_files.invoke({"pattern": pattern, "path": path}))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def run_command(command: str) -> str:
    """Run a shell command."""
    try:
        # run_shell_command is async
        return _truncate(await run_shell_command.ainvoke({"command": command}))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def save_file(path: str, content: str) -> str:
    """Write content to a file."""
    try:
        # write_file_content tool expects dict? langchain tool with one arg usually takes it directly if using invoke with primitives? 
        # But here we invoke the underlying func? No, `invoke`.
        # let's try direct invoke with dict
        return write_file_content.invoke({"path": path, "content": content})
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def search_web(query: str) -> str:
    """Search the web using Brave Search."""
    # Settings might not have BRAVE_API_KEY directly if it's not defined in Config?
    # Checking if settings object has it.
    # Assuming it's in os.environ via .env if not in settings model
    api_key = getattr(settings, "BRAVE_API_KEY", os.getenv("BRAVE_API_KEY"))
    
    if not api_key:
        return "Error: BRAVE_API_KEY not configured."
    
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
    params = {"q": query}
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            return f"Error: Brave API returned {resp.status_code} {resp.text}"
        data = resp.json()
        
    # Simplify output
    results = []
    if "web" in data and "results" in data["web"]:
        for item in data["web"]["results"][:5]:
            results.append(f"- [{item.get('title')}]({item.get('url')}): {item.get('description')}")
            
    return _truncate("\n".join(results) if results else "No results found.")


@mcp.tool()
def read_document(path: str) -> str:
    """Read content from PDF or DOCX file."""
    if not os.path.exists(path):
        return f"Error: File {path} not found."
    
    ext = os.path.splitext(path)[1].lower()
    
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(path)
            text = []
            for page in reader.pages:
                text.append(page.extract_text())
            return "\n".join(text)
            
        elif ext == ".docx":
            import docx
            doc = docx.Document(path)
            text = []
            for para in doc.paragraphs:
                text.append(para.text)
            return "\n".join(text)
            
        else:
            # Fallback to plain text read
            with open(path, "r", errors="ignore") as f:
                return _truncate(f.read())
                
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
        return json.dumps(result, indent=2)
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
