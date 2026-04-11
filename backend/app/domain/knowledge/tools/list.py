"""
kb_list - List documents in the knowledge base (like ls/find).
"""

import logging
from datetime import datetime
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg
from pydantic import Field

from app.core.tools import evoloop_tool
from app.domain.knowledge.services.store import KnowledgeStoreService

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "列出知识文档", "en": "List Knowledge Documents"}
)
async def kb_list(
    collection: Annotated[str, Field(default="", description="Filter by collection name")] = "",
    path: Annotated[str, Field(default="", description="Filter by subdirectory path")] = "",
    pattern: Annotated[str, Field(default="", description="Filter by filename pattern (substring match)")] = "",
    limit: Annotated[int, Field(default=50, ge=1, le=200, description="Maximum results")] = 50,
    tree: Annotated[bool, Field(default=False, description="Show directory tree structure")] = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    List documents in the knowledge base.
    
    This is similar to 'ls' or 'find' command - it lists documents
    with optional filtering and tree structure.
    
    Examples:
        - List all: kb_list()
        - By collection: kb_list(collection="backend")
        - With pattern: kb_list(pattern="auth")
        - Tree view: kb_list(collection="myapp", tree=True)
    
    Args:
        collection: Filter by collection name
        path: Filter by subdirectory path
        pattern: Filter by filename pattern (substring match)
        limit: Maximum results to return (default: 50, max: 200)
        tree: Show directory tree structure (default: false)
    
    Returns:
        List of documents with metadata.
    """
    store = KnowledgeStoreService()
    
    try:
        # Get documents
        search_collection = collection or None
        documents = store.list_documents(search_collection)
        
        # Apply filters
        if path:
            documents = [
                d for d in documents
                if path in d.get('path', '')
            ]
        
        if pattern:
            documents = [
                d for d in documents
                if pattern.lower() in d.get('path', '').lower()
                or pattern.lower() in d.get('title', '').lower()
            ]
        
        # Sort by updated_at (most recent first)
        documents.sort(
            key=lambda d: d.get('updated_at', ''),
            reverse=True
        )
        
        # Apply limit
        total_count = len(documents)
        documents = documents[:limit]
        
        # Format output
        if tree:
            return _format_tree(documents, collection)
        else:
            return _format_list(documents, total_count, limit)
    
    except Exception as e:
        logger.error(f"kb_list failed: {e}")
        return f"List error: {str(e)}"


def _format_list(documents: list, total: int, limit: int) -> str:
    """Format as flat list."""
    if not documents:
        return "No documents found in the knowledge base."
    
    lines = []
    lines.append(f"Knowledge Base ({total} total, showing {min(len(documents), limit)})")
    lines.append("")
    
    # Group by collection
    by_collection = {}
    for doc in documents:
        proj = doc.get('collection', 'general')
        if proj not in by_collection:
            by_collection[coll] = []
        by_collection[coll].append(doc)
    
    # Display by collection
    for coll, docs in sorted(by_collection.items()):
        lines.append(f"[{proj}/]")
        
        for doc in docs:
            title = doc.get('title', 'Untitled')
            doc_path = doc.get('path', '')
            doc_type = doc.get('doc_type', 'doc')
            
            # Get file icon based on type
            icon = _get_icon(doc_type)
            
            # Format date
            updated = doc.get('updated_at', '')
            if updated:
                try:
                    dt = datetime.fromisoformat(updated)
                    date_str = dt.strftime("%Y-%m-%d")
                except:
                    date_str = updated[:10] if len(updated) >= 10 else updated
            else:
                date_str = "unknown"
            
            lines.append(f"   {icon} {title}")
            lines.append(f"      Path: {doc_path}")
            lines.append(f"      Updated: {date_str}")
        
        lines.append("")
    
    if total > limit:
        lines.append(f"... and {total - limit} more documents")
    
    return "\n".join(lines)


def _format_tree(documents: list, collection: str) -> str:
    """Format as tree structure."""
    if not documents:
        return "No documents found."
    
    lines = []
    lines.append("Knowledge Base Tree")
    lines.append("")
    
    # Build tree
    tree = {}
    for doc in documents:
        path = doc.get('path', '')
        parts = path.split('/')
        
        current = tree
        for part in parts[:-1]:
            if part not in current:
                current[part] = {"__files__": []}
            current = current[part]
        
        if "__files__" not in current:
            current["__files__"] = []
        
        current["__files__"].append({
            "name": parts[-1],
            "title": doc.get('title', 'Untitled'),
            "type": doc.get('doc_type', 'doc')
        })
    
    # Render tree
    _render_tree(tree, lines, "")
    
    return "\n".join(lines)


def _render_tree(node: dict, lines: list, prefix: str):
    """Recursively render tree."""
    # Sort directories and files
    dirs = sorted([k for k in node.keys() if k != "__files__"])
    files = sorted(node.get("__files__", []), key=lambda f: f["name"])
    
    # Render directories
    for i, dirname in enumerate(dirs):
        is_last = (i == len(dirs) - 1) and not files
        connector = "`-- " if is_last else "|-- "
        lines.append(f"{prefix}{connector}[{dirname}/]")
        
        new_prefix = prefix + ("    " if is_last else "|   ")
        _render_tree(node[dirname], lines, new_prefix)
    
    # Render files
    for i, file in enumerate(files):
        is_last = i == len(files) - 1
        connector = "`-- " if is_last else "|-- "
        icon = _get_icon(file["type"])
        lines.append(f"{prefix}{connector}{icon} {file['name']}")


def _get_icon(doc_type: str) -> str:
    """Get label for document type."""
    labels = {
        'doc': '[DOC]',
        'code': '[CODE]',
        'guide': '[GUIDE]',
        'api': '[API]',
        'design': '[DESIGN]',
        'architecture': '[ARCH]',
        'requirement': '[REQ]',
    }
    return labels.get(doc_type, '[DOC]')
