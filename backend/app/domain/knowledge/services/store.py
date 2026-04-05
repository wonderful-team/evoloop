"""
Knowledge store service for file operations.
"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from app.core.config import settings
from app.domain.knowledge.models import DocumentMetadata, MarkdownDocument
from app.utils.file import (
    get_file_stats,
    read_file_content,
    write_file_contents,
)

logger = logging.getLogger(__name__)


class KnowledgeStoreService:
    """
    Service for storing and retrieving knowledge documents.
    
    This service manages the file system layout:
    - raw/      : Markdown documents
    - meta/     : Metadata JSON files
    - temp/     : Temporary uploads
    
    Usage:
        store = KnowledgeStoreService()
        
        # Save a document
        await store.save_document(doc, metadata, project="my-project")
        
        # Read a document
        content = store.read_document("my-project/guide.md")
        
        # List documents
        docs = store.list_documents("my-project")
    """
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize the store.
        
        Args:
            base_path: Base directory for knowledge storage.
                      Defaults to ~/.evoloop/knowledge
        """
        if base_path:
            self.base_path = Path(base_path)
        else:
            self.base_path = Path.home() / ".evoloop" / "knowledge"
        
        # Ensure directories exist
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Create necessary directories."""
        (self.base_path / "raw").mkdir(parents=True, exist_ok=True)
        (self.base_path / "meta").mkdir(parents=True, exist_ok=True)
        (self.base_path / "temp").mkdir(parents=True, exist_ok=True)
    
    # ==========================================================================
    # Document Operations
    # ==========================================================================
    
    def save_document(
        self,
        document: MarkdownDocument,
        metadata: Optional[DocumentMetadata] = None,
        project: str = "default",
        path: Optional[str] = None
    ) -> str:
        """
        Save a document to the knowledge base.
        
        Args:
            document: The document to save
            metadata: Optional metadata
            project: Project name (creates subdirectory)
            path: Relative path within project (auto-generated if None)
        
        Returns:
            The relative path where the document was saved
        """
        # Generate path if not provided
        if path is None:
            path = self._generate_path(document.source, project)
        
        # Ensure .md extension
        if not path.endswith('.md'):
            path += '.md'
        
        # Full paths
        raw_path = self.base_path / "raw" / project / path
        meta_path = self.base_path / "meta" / project / f"{path}.json"
        
        # Create directories
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save document with frontmatter
        content_with_frontmatter = document.to_frontmatter()
        write_file_contents(content_with_frontmatter, str(raw_path))
        
        # Save metadata
        if metadata:
            meta_dict = metadata.to_dict()
        else:
            meta_dict = {
                "source_file": document.source,
                "source_mime_type": document.mime_type,
                "file_size_bytes": document.size,
                "extracted_at": document.extracted_at.isoformat()
            }
        
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_dict, f, indent=2, ensure_ascii=False)
        
        relative_path = f"{project}/{path}"
        logger.info(f"Saved document to {relative_path}")
        
        # Return document info for FTS indexing
        return {
            "path": relative_path,
            "title": document.metadata.get("title", document.source),
            "content": document.content,
            "project": project,
            "size": document.size,
            "word_count": len(document.content.split())
        }
    
    def read_document(
        self,
        path: str,
        offset: int = 0,
        limit: Optional[int] = None
    ) -> dict:
        """
        Read a document with pagination support.
        
        Args:
            path: Relative path (e.g., "my-project/guide.md")
            offset: Line offset (0-based)
            limit: Maximum lines to read
        
        Returns:
            Dict with content, metadata, and pagination info
        """
        full_path = self.base_path / "raw" / path
        
        if not full_path.exists():
            raise FileNotFoundError(f"Document not found: {path}")
        
        # Read content with pagination
        content, encoding, meta = read_file_content(
            str(full_path),
            start_line=offset + 1,  # read_file_content uses 1-based
            limit=limit
        )
        
        # Parse frontmatter
        doc = MarkdownDocument.from_frontmatter(content)
        
        # Load metadata
        meta_path = self.base_path / "meta" / f"{path}.json"
        metadata = None
        if meta_path.exists():
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load metadata for {path}: {e}")
        
        return {
            "content": doc.content,
            "frontmatter": doc.metadata,
            "extracted_metadata": metadata,
            "path": path,
            "encoding": encoding,
            "offset": offset,
            "limit": limit,
            "total_lines": meta.get("total_lines", doc.line_count),
            "has_more": meta.get("has_more", False),
            "content_hash": meta.get("content_hash")
        }
    
    def delete_document(self, path: str) -> bool:
        """
        Delete a document and its metadata.
        
        Args:
            path: Relative path to document
        
        Returns:
            True if document was deleted
        """
        raw_path = self.base_path / "raw" / path
        meta_path = self.base_path / "meta" / f"{path}.json"
        
        deleted = False
        
        if raw_path.exists():
            raw_path.unlink()
            deleted = True
            logger.info(f"Deleted document: {path}")
        
        if meta_path.exists():
            meta_path.unlink()
        
        return deleted
    
    # ==========================================================================
    # Listing and Search
    # ==========================================================================
    
    def list_documents(
        self,
        project: Optional[str] = None,
        pattern: str = "*.md"
    ) -> list[dict]:
        """
        List documents in the knowledge base.
        
        Args:
            project: Filter by project (None = all projects)
            pattern: Glob pattern for filtering
        
        Returns:
            List of document info dictionaries with tags
        """
        if project:
            search_path = self.base_path / "raw" / project
        else:
            search_path = self.base_path / "raw"
        
        if not search_path.exists():
            return []
        
        documents = []
        doc_tags_map = {}  # Cache tags from SQLite
        
        # Load tags from SQLite
        try:
            db_path = self.base_path / "search.db"
            if db_path.exists():
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT doc_id, tag FROM doc_tags")
                for row in cursor:
                    doc_id = row["doc_id"]
                    if doc_id not in doc_tags_map:
                        doc_tags_map[doc_id] = []
                    doc_tags_map[doc_id].append(row["tag"])
                conn.close()
        except Exception as e:
            logger.warning(f"Failed to load tags from SQLite: {e}")
        
        for file_path in search_path.rglob(pattern):
            if not file_path.is_file():
                continue
            
            rel_path = file_path.relative_to(self.base_path / "raw")
            doc_id = str(rel_path)
            
            # Get file stats
            try:
                stats = file_path.stat()
                meta_path = self.base_path / "meta" / f"{rel_path}.json"
                
                doc_info = {
                    "path": doc_id,
                    "size_bytes": stats.st_size,
                    "modified_at": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                    "has_metadata": meta_path.exists(),
                    "tags": doc_tags_map.get(doc_id, [])  # Add tags from SQLite
                }
                
                # Try to load title from metadata
                if meta_path.exists():
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            doc_info["title"] = meta.get("title", file_path.stem)
                            doc_info["source"] = meta.get("source_file")
                    except Exception:
                        doc_info["title"] = file_path.stem
                else:
                    doc_info["title"] = file_path.stem
                
                documents.append(doc_info)
            except Exception as e:
                logger.warning(f"Failed to stat {file_path}: {e}")
        
        # Sort by modified time (newest first)
        documents.sort(key=lambda x: x["modified_at"], reverse=True)
        return documents
    
    def search_documents(
        self,
        query: str,
        project: Optional[str] = None,
        context_lines: int = 2
    ) -> Iterator[dict]:
        """
        Simple text search across documents (generator).
        
        This is a basic grep-like search. For production, consider
        using a proper search engine like Elasticsearch or SQLite FTS.
        
        Args:
            query: Search string (case-insensitive)
            project: Limit search to project
            context_lines: Lines of context around matches
        
        Yields:
            Dict with match info
        """
        import re
        
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        
        if project:
            search_path = self.base_path / "raw" / project
        else:
            search_path = self.base_path / "raw"
        
        if not search_path.exists():
            return
        
        for file_path in search_path.rglob("*.md"):
            if not file_path.is_file():
                continue
            
            try:
                content = file_path.read_text(encoding='utf-8')
                lines = content.split('\n')
                
                matches = []
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        # Get context
                        start = max(0, i - context_lines)
                        end = min(len(lines), i + context_lines + 1)
                        context = '\n'.join(lines[start:end])
                        
                        matches.append({
                            "line": i + 1,
                            "text": line.strip(),
                            "context": context
                        })
                
                if matches:
                    rel_path = file_path.relative_to(self.base_path / "raw")
                    yield {
                        "path": str(rel_path),
                        "match_count": len(matches),
                        "matches": matches
                    }
            except Exception as e:
                logger.warning(f"Failed to search {file_path}: {e}")
    
    # ==========================================================================
    # Project Management
    # ==========================================================================
    
    def list_projects(self) -> list[str]:
        """List all projects (subdirectories in raw/)."""
        raw_path = self.base_path / "raw"
        if not raw_path.exists():
            return []
        
        projects = []
        for item in raw_path.iterdir():
            if item.is_dir():
                projects.append(item.name)
        
        return sorted(projects)
    
    def create_project(self, name: str) -> Path:
        """Create a new project directory."""
        project_raw = self.base_path / "raw" / name
        project_meta = self.base_path / "meta" / name
        
        project_raw.mkdir(parents=True, exist_ok=True)
        project_meta.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Created project: {name}")
        return project_raw
    
    def delete_project(self, name: str) -> bool:
        """Delete a project and all its documents."""
        project_raw = self.base_path / "raw" / name
        project_meta = self.base_path / "meta" / name
        
        deleted = False
        
        if project_raw.exists():
            shutil.rmtree(project_raw)
            deleted = True
        
        if project_meta.exists():
            shutil.rmtree(project_meta)
        
        if deleted:
            logger.info(f"Deleted project: {name}")
        
        return deleted
    
    # ==========================================================================
    # Helpers
    # ==========================================================================
    
    def _generate_path(self, original_filename: str, project: str) -> str:
        """Generate a safe path for saving."""
        import re
        
        # Remove extension and sanitize
        name = Path(original_filename).stem
        name = re.sub(r'[^\w\s-]', '', name)  # Remove special chars
        name = re.sub(r'[-\s]+', '-', name)   # Collapse spaces/hyphens
        name = name.strip('-').lower()
        
        if not name:
            name = "untitled"
        
        # Add timestamp if file exists
        base_path = self.base_path / "raw" / project / f"{name}.md"
        if base_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            name = f"{name}-{timestamp}"
        
        return f"{name}.md"
    
    def get_stats(self) -> dict:
        """Get storage statistics."""
        stats = {
            "total_documents": 0,
            "total_size_bytes": 0,
            "projects": {}
        }
        
        for project in self.list_projects():
            project_path = self.base_path / "raw" / project
            project_docs = list(project_path.rglob("*.md"))
            project_size = sum(f.stat().st_size for f in project_docs)
            
            stats["projects"][project] = {
                "documents": len(project_docs),
                "size_bytes": project_size
            }
            stats["total_documents"] += len(project_docs)
            stats["total_size_bytes"] += project_size
        
        return stats
