"""
Knowledge store service for file operations.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from app.domain.knowledge.models import DocumentMetadata, MarkdownDocument
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.file import (
    read_file_content,
    write_file_contents,
)

logger = logging.getLogger(__name__)


class DocumentSaveResult(DynamicBaseModel):
    """Result of saving a document to the knowledge base."""
    path: str
    title: str
    content: str
    collection: str
    size: int
    word_count: int
    source_project_id: Optional[int] = None


class DocumentReadResult(DynamicBaseModel):
    """Result of reading a document from the knowledge base."""
    content: str
    frontmatter: dict
    extracted_metadata: Optional[dict] = None
    path: str
    encoding: str
    offset: int
    limit: Optional[int] = None
    total_lines: int
    has_more: bool
    content_hash: Optional[str] = None


class DocumentListItem(DynamicBaseModel):
    """Item in a document list from the knowledge base."""
    path: str
    size_bytes: int
    modified_at: str
    has_metadata: bool
    tags: list[str]
    title: str
    source: Optional[str] = None
    source_project_id: Optional[int] = None


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
        await store.save_document(doc, metadata, collection="my-collection")
        
        # Read a document
        content = store.read_document("my-collection/guide.md")
        
        # List documents
        docs = store.list_documents("my-collection")
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
        (self.base_path / "versions").mkdir(parents=True, exist_ok=True)
    
    # ==========================================================================
    # Document Operations
    # ==========================================================================
    
    def save_document(
        self,
        document: MarkdownDocument,
        metadata: Optional[DocumentMetadata] = None,
        collection: str = "default",
        path: Optional[str] = None,
        source_project_id: Optional[int] = None
    ) -> DocumentSaveResult:
        """
        Save a document to the knowledge base.

        Args:
            document: The document to save
            metadata: Optional metadata
            collection: Collection name (creates subdirectory)
            path: Relative path within collection (auto-generated if None)
            source_project_id: Optional workspace project ID to associate with

        Returns:
            The relative path where the document was saved
        """
        # Generate path if not provided
        if path is None:
            path = self._generate_path(document.source, collection)
        
        # Ensure .md extension
        if not path.endswith('.md'):
            path += '.md'
        
        # Full paths
        raw_path = self.base_path / "raw" / collection / path
        meta_path = self.base_path / "meta" / collection / f"{path}.json"

        # Create directories
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.parent.mkdir(parents=True, exist_ok=True)

        # T-3.2: Backup existing version before overwrite
        if raw_path.exists():
            self._backup_version(raw_path, collection, path)

        # Save document with frontmatter
        content_with_frontmatter = document.to_frontmatter()
        write_file_contents(content_with_frontmatter, str(raw_path))
        
        # Save metadata
        if metadata:
            meta_dict = metadata.model_dump(mode="json")
        else:
            meta_dict = {
                "source_file": document.source,
                "source_mime_type": document.mime_type,
                "file_size_bytes": document.size,
                "extracted_at": document.extracted_at.isoformat()
            }

        # Add source project ID if provided
        if source_project_id:
            meta_dict["source_project_id"] = source_project_id
        
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_dict, f, indent=2, ensure_ascii=False)
        
        relative_path = f"{collection}/{path}"
        logger.info(f"Saved document to {relative_path}")
        
        # Return document info for FTS indexing
        return DocumentSaveResult(
            path=relative_path,
            title=document.metadata.get("title", document.source),
            content=document.content,
            collection=collection,
            size=document.size,
            word_count=len(document.content.split()),
            source_project_id=source_project_id,
        )
    
    def read_documents_batch(
        self,
        paths: list[str],
        offset: int = 0,
        limit: Optional[int] = None
    ) -> dict[str, DocumentReadResult]:
        """Batch read multiple documents to reduce file open/close overhead.

        Returns a dict mapping path -> DocumentReadResult for successfully
        read documents. Failed reads are logged and skipped.
        """
        results: dict[str, DocumentReadResult] = {}
        for path in paths:
            try:
                results[path] = self.read_document(path, offset=offset, limit=limit)
            except Exception as e:
                logger.warning(f"Batch read failed for {path}: {e}")
        return results

    def read_document(
        self,
        path: str,
        offset: int = 0,
        limit: Optional[int] = None
    ) -> DocumentReadResult:
        """
        Read a document with pagination support.
        
        Args:
            path: Relative path (e.g., "my-collection/guide.md")
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
        
        return DocumentReadResult(
            content=doc.content,
            frontmatter=doc.metadata,
            extracted_metadata=metadata,
            path=path,
            encoding=encoding,
            offset=offset,
            limit=limit,
            total_lines=meta.get("total_lines", doc.line_count),
            has_more=meta.get("has_more", False),
            content_hash=meta.get("content_hash"),
        )
    
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

    def get_tags_batch(self, doc_ids: list[str]) -> dict[str, list[str]]:
        """Batch load tags from SQLite for multiple documents in a single query."""
        if not doc_ids:
            return {}
        
        tags_map: dict[str, list[str]] = {}
        try:
            db_path = self.base_path / "search.db"
            if not db_path.exists():
                return tags_map
            
            import sqlite3
            placeholders = ",".join(["?"] * len(doc_ids))
            with sqlite3.connect(str(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                for row in conn.execute(
                    f"SELECT doc_id, tag FROM doc_tags WHERE doc_id IN ({placeholders})",
                    doc_ids
                ):
                    tags_map.setdefault(row["doc_id"], []).append(row["tag"])
        except Exception as e:
            logger.warning(f"Failed to batch load tags: {e}")
        
        return tags_map
    
    def list_documents(
        self,
        collection: Optional[str] = None,
        pattern: str = "*.md",
        source_project_id: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[DocumentListItem]:
        """
        List documents in the knowledge base.

        Args:
            collection: Filter by collection (None = all collections)
            pattern: Glob pattern for filtering
            source_project_id: Filter by workspace project ID

        Returns:
            List of document info dictionaries with tags
        """
        if collection:
            search_path = self.base_path / "raw" / collection
        else:
            search_path = self.base_path / "raw"
        
        if not search_path.exists():
            return []
        
        documents = []
        
        # First pass: collect all documents and doc_ids
        for file_path in search_path.rglob(pattern):
            if not file_path.is_file():
                continue
            
            rel_path = file_path.relative_to(self.base_path / "raw")
            doc_id = str(rel_path)
            
            # Get file stats
            try:
                stats = file_path.stat()
                meta_path = self.base_path / "meta" / f"{rel_path}.json"
                
                doc_info = DocumentListItem(
                    path=doc_id,
                    size_bytes=stats.st_size,
                    modified_at=datetime.fromtimestamp(stats.st_mtime).isoformat(),
                    has_metadata=meta_path.exists(),
                    tags=[],  # Will be filled after batch load
                    title=file_path.stem,
                )

                # Try to load title from metadata
                doc_source_project_id = None
                if meta_path.exists():
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            doc_info.title = meta.get("title", file_path.stem)
                            doc_info.source = meta.get("source_file")
                            doc_source_project_id = meta.get("source_project_id")
                    except Exception:
                        pass

                # Filter by source_project_id if specified
                if source_project_id is not None:
                    if doc_source_project_id != source_project_id:
                        continue
                doc_info.source_project_id = doc_source_project_id

                documents.append(doc_info)
            except Exception as e:
                logger.warning(f"Failed to stat {file_path}: {e}")
        
        # Batch load tags from SQLite (single query instead of N+1)
        if documents:
            doc_tags_map = self.get_tags_batch([d.path for d in documents])
            for doc in documents:
                doc.tags = doc_tags_map.get(doc.path, [])
        
        # Sort by modified time (newest first)
        documents.sort(key=lambda x: x.modified_at, reverse=True)

        # Apply pagination
        if offset:
            documents = documents[offset:]
        if limit is not None:
            documents = documents[:limit]

        return documents
    
    def search_documents(
        self,
        query: str,
        collection: Optional[str] = None,
        context_lines: int = 2
    ) -> Iterator[dict]:
        """
        Simple text search across documents (generator).
        
        This is a basic grep-like search. For production, consider
        using a proper search engine like Elasticsearch or SQLite FTS.
        
        Args:
            query: Search string (case-insensitive)
            collection: Limit search to collection
            context_lines: Lines of context around matches
        
        Yields:
            Dict with match info
        """
        import re
        
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        
        if collection:
            search_path = self.base_path / "raw" / collection
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
    # Collection Management
    # ==========================================================================
    
    def list_collections(self) -> list[str]:
        """List all collections (subdirectories in raw/)."""
        raw_path = self.base_path / "raw"
        if not raw_path.exists():
            return []
        
        collections = []
        for item in raw_path.iterdir():
            if item.is_dir():
                collections.append(item.name)
        
        return sorted(collections)
    
    def create_collections(self, name: str) -> Path:
        """Create a new collection directory."""
        project_raw = self.base_path / "raw" / name
        project_meta = self.base_path / "meta" / name
        
        project_raw.mkdir(parents=True, exist_ok=True)
        project_meta.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Created collection: {name}")
        return project_raw
    
    def delete_project(self, name: str) -> bool:
        """Delete a collection and all its documents."""
        project_raw = self.base_path / "raw" / name
        project_meta = self.base_path / "meta" / name
        
        deleted = False
        
        if project_raw.exists():
            shutil.rmtree(project_raw)
            deleted = True
        
        if project_meta.exists():
            shutil.rmtree(project_meta)
        
        if deleted:
            logger.info(f"Deleted collection: {name}")
        
        return deleted
    
    # ==========================================================================
    # Helpers
    # ==========================================================================
    
    def _generate_path(self, original_filename: str, collection: str) -> str:
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
        base_path = self.base_path / "raw" / collection / f"{name}.md"
        if base_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            name = f"{name}-{timestamp}"
        
        return f"{name}.md"
    
    def _backup_version(self, raw_path: Path, collection: str, path: str) -> None:
        """Backup current document version before overwrite (T-3.2).

        Retains only the last 10 versions to prevent unbounded growth.
        """
        try:
            version_dir = self.base_path / "versions" / collection / path
            version_dir.mkdir(parents=True, exist_ok=True)
            # Use millisecond-precision timestamp to avoid collisions during rapid ops
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            backup_path = version_dir / f"{timestamp}.md"
            shutil.copy2(raw_path, backup_path)
            logger.debug(f"Backed up version: {backup_path}")

            # Retention: keep only last 10 versions
            MAX_VERSIONS = 10
            versions = sorted(version_dir.glob("*.md"), key=lambda p: p.name)
            if len(versions) > MAX_VERSIONS:
                for old in versions[:-MAX_VERSIONS]:
                    old.unlink()
                    logger.debug(f"Removed old version: {old}")
        except Exception as e:
            logger.warning(f"Failed to backup version for {path}: {e}")

    def get_document_versions(self, doc_path: str) -> list[dict]:
        """List version history for a document (T-3.2).

        Args:
            doc_path: Relative path (e.g. "collection/doc.md")

        Returns:
            List of version dicts with timestamp and path
        """
        version_dir = self.base_path / "versions" / doc_path
        if not version_dir.exists():
            return []

        versions = []
        for vfile in sorted(version_dir.glob("*.md"), reverse=True):
            timestamp_str = vfile.stem
            try:
                # Parse millisecond-precision timestamp
                if "_" in timestamp_str and len(timestamp_str.split("_")[-1]) == 3:
                    ts = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S_%f")
                else:
                    ts = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                versions.append({
                    "timestamp": timestamp_str,
                    "iso_time": ts.isoformat(),
                    "path": str(vfile),
                    "size_bytes": vfile.stat().st_size,
                })
            except ValueError:
                continue
        return versions

    def restore_document_version(self, doc_path: str, timestamp: str) -> bool:
        """Restore a document to a previous version (T-3.2).

        Args:
            doc_path: Relative path (e.g. "collection/doc.md")
            timestamp: Version timestamp string (e.g. "20240420_123456")

        Returns:
            True if restored successfully
        """
        version_file = self.base_path / "versions" / doc_path / f"{timestamp}.md"
        target_path = self.base_path / "raw" / doc_path

        if not version_file.exists():
            logger.warning(f"Version not found: {version_file}")
            return False

        try:
            # Backup current before restoring
            if target_path.exists():
                self._backup_version(target_path, *doc_path.split("/", 1))
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(version_file, target_path)
            logger.info(f"Restored {doc_path} to version {timestamp}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore version: {e}")
            return False

    def get_stats(self) -> dict:
        """Get storage statistics."""
        stats = {
            "total_documents": 0,
            "total_size_bytes": 0,
            "collections": {},
            "total_versions": 0,
        }

        for collection in self.list_collections():
            project_path = self.base_path / "raw" / collection
            project_docs = list(project_path.rglob("*.md"))
            project_size = sum(f.stat().st_size for f in project_docs)

            stats["collections"][collection] = {
                "documents": len(project_docs),
                "size_bytes": project_size
            }
            stats["total_documents"] += len(project_docs)
            stats["total_size_bytes"] += project_size

        # Count versions
        version_root = self.base_path / "versions"
        if version_root.exists():
            stats["total_versions"] = sum(1 for _ in version_root.rglob("*.md"))

        return stats


# Singleton instance
_store_service: Optional[KnowledgeStoreService] = None


def get_store_service() -> KnowledgeStoreService:
    """Get or create store service singleton with config support."""
    global _store_service
    if _store_service is None:
        try:
            from app.core.config import settings
            base_path = settings.KNOWLEDGE_BASE_PATH
        except Exception:
            base_path = None
        _store_service = KnowledgeStoreService(base_path=base_path)
    return _store_service
