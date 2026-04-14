"""
kb_read - Read documents from the knowledge base (like cat/less).
"""

import logging
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, Field

from app.core.tools import evoloop_tool
from app.domain.knowledge.services.citations import get_citation_tracker
from app.domain.knowledge.services.store import KnowledgeStoreService

logger = logging.getLogger(__name__)


class KBReadInput(BaseModel):
    """Input for kb_read tool."""
    path: str = Field(
        description="Path to the document (e.g., 'guides/auth.md' or 'collection/api/guide.md')"
    )
    offset: int = Field(
        default=0,
        description="Line offset to start reading from (0-based)"
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of lines to read (max 500)"
    )
    collection: str = Field(
        default="",
        description="Collection name (if not included in path)"
    )


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "读取知识文档", "en": "Read Knowledge Document"}
)
async def kb_read(
    path: Annotated[str, Field(description="Path to the document")],
    offset: Annotated[int, Field(default=0, description="Line offset (0-based)")] = 0,
    limit: Annotated[int, Field(default=100, ge=1, le=500, description="Max lines to read")] = 100,
    collection: Annotated[str, Field(default="", description="Collection name")] = "",
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Read a document from the knowledge base with pagination support.
    
    This is similar to 'cat' or 'less' command - it outputs the content
    of a knowledge base document. Use offset and limit for pagination.
    
    Examples:
        - Read full document: kb_read(path="guides/auth.md")
        - Read specific lines: kb_read(path="guides/auth.md", offset=50, limit=20)
        - Read collection doc: kb_read(path="api/README.md", collection="my-api")
    
    Args:
        path: Path to the document (e.g., "guides/auth.md")
        offset: Line number to start from (0-based, default: 0)
        limit: Maximum lines to read (default: 100, max: 500)
        collection: Collection name (if not included in path)
    
    Returns:
        Document content with line numbers and pagination info.
    """
    store = KnowledgeStoreService()
    
    try:
        # Normalize path
        if collection and not path.startswith(collection):
            full_path = f"{collection}/{path}"
        else:
            full_path = path
        
        # Ensure .md extension
        if not full_path.endswith('.md'):
            full_path += '.md'
        
        # Read document
        result = store.read_document(full_path, offset=offset, limit=limit)
        
        # Record citation (async, non-blocking)
        try:
            tracker = get_citation_tracker()
            await tracker.record_citation(
                doc_path=full_path,
                tool_used="kb_read",
                session_id=config.get("configurable", {}).get("thread_id") if config else None
            )
        except Exception:
            pass  # Don't fail if citation tracking fails
        
        # Format output
        lines = []
        content_lines = result['content'].split('\n')
        start_line = result['offset'] + 1
        
        # Header
        lines.append(f"File: {full_path}")
        lines.append(f"   Lines {start_line}-{start_line + len(content_lines) - 1} of {result['total_lines']}")
        lines.append("")
        
        # Content with line numbers
        for i, line in enumerate(content_lines):
            lines.append(f"{start_line + i:4d} | {line}")
        
        # Footer
        if result['has_more']:
            next_offset = result['offset'] + result['limit']
            lines.append("")
            lines.append(f"... (more content available, use offset={next_offset} to continue)")
        
        return "\n".join(lines)
    
    except FileNotFoundError:
        return f"Document not found: {path}\n\nUse kb_list() to see available documents."
    
    except Exception as e:
        logger.error(f"kb_read failed: {e}")
        return f"Error reading document: {str(e)}"
