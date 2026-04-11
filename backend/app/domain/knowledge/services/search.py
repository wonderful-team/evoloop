"""
Full-text search service using SQLite FTS5.

Provides fast full-text search over knowledge base documents with:
- BM25 ranking
- Chinese text support (via external tokenizer if available)
- Highlight snippets
- Faceted search by collection/tags
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Single search result."""
    doc_id: str
    path: str
    collection: str
    title: str
    content_snippet: str
    highlights: str  # HTML with <mark> tags
    rank: float
    bm25_score: float


@dataclass
class SearchResults:
    """Collection of search results."""
    query: str
    total: int
    results: list[SearchResult]
    facets: dict  # collection counts, tag counts, etc.


class FTSService:
    """
    SQLite FTS5 search service for knowledge base.
    
    Usage:
        fts = FTSService()
        await fts.initialize()
        
        # Index a document
        await fts.index_document("collection/doc.md", "Document Title", "content...", collection="myapp")
        
        # Search
        results = await fts.search("authentication", limit=20)
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize FTS service.
        
        Args:
            db_path: Path to SQLite database. Defaults to ~/.evoloop/knowledge/search.db
        """
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".evoloop" / "knowledge" / "search.db"
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[sqlite3.Connection] = None
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    async def initialize(self) -> None:
        """Initialize FTS tables and indexes."""
        conn = self._get_connection()
        
        # Check if FTS5 is available
        try:
            conn.execute("SELECT * FROM sqlite_master WHERE type='table' AND name='fts_documents'")
        except sqlite3.OperationalError as e:
            if "fts5" in str(e).lower():
                logger.error("FTS5 extension not available. Please compile SQLite with FTS5.")
                raise RuntimeError("FTS5 not available")
        
        # Create FTS5 virtual table for documents
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_documents USING fts5(
                doc_id,
                path,
                collection,
                title,
                content,
                tags,
                tokenize='porter unicode61'
            )
        """)
        
        # Create auxiliary table for metadata (FTS5 doesn't store arbitrary data)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_metadata (
                doc_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                collection TEXT NOT NULL DEFAULT 'default',
                title TEXT,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_size INTEGER,
                word_count INTEGER
            )
        """)
        
        # Create indexes for faceted search
        conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_project ON doc_metadata(collection)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_path ON doc_metadata(path)")
        
        # Create tags table for many-to-many relationship
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_tags (
                doc_id TEXT,
                tag TEXT,
                PRIMARY KEY (doc_id, tag),
                FOREIGN KEY (doc_id) REFERENCES doc_metadata(doc_id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tag ON doc_tags(tag)")
        
        # Create search history for analytics
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                results_count INTEGER,
                searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id TEXT
            )
        """)
        
        conn.commit()
        logger.info(f"FTS database initialized at {self.db_path}")
    
    async def index_document(
        self,
        doc_id: str,
        path: str,
        title: str,
        content: str,
        collection: str = "default",
        tags: Optional[list[str]] = None,
        file_size: Optional[int] = None,
        word_count: Optional[int] = None
    ) -> bool:
        """
        Index or update a document in FTS.
        
        Args:
            doc_id: Unique document ID (usually collection/path)
            path: File path
            title: Document title
            content: Full text content
            collection: Collection name
            tags: List of tags
            file_size: File size in bytes
            word_count: Word count
        
        Returns:
            True if indexed successfully
        """
        conn = self._get_connection()
        
        try:
            # Delete existing entry if any
            conn.execute("DELETE FROM fts_documents WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM doc_metadata WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM doc_tags WHERE doc_id = ?", (doc_id,))
            
            # Insert into FTS table
            tags_str = ",".join(tags or [])
            conn.execute(
                "INSERT INTO fts_documents (doc_id, path, collection, title, content, tags) VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, path, collection, title, content, tags_str)
            )
            
            # Insert metadata
            conn.execute(
                """INSERT INTO doc_metadata 
                   (doc_id, path, collection, title, indexed_at, file_size, word_count) 
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)""",
                (doc_id, path, collection, title, file_size, word_count)
            )
            
            # Insert tags
            if tags:
                conn.executemany(
                    "INSERT INTO doc_tags (doc_id, tag) VALUES (?, ?)",
                    [(doc_id, tag) for tag in tags]
                )
            
            conn.commit()
            logger.debug(f"Indexed document: {doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index document {doc_id}: {e}")
            conn.rollback()
            return False
    
    async def remove_document(self, doc_id: str) -> bool:
        """Remove a document from the index."""
        conn = self._get_connection()
        
        try:
            conn.execute("DELETE FROM fts_documents WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM doc_metadata WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM doc_tags WHERE doc_id = ?", (doc_id,))
            conn.commit()
            logger.debug(f"Removed document from index: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove document {doc_id}: {e}")
            conn.rollback()
            return False
    
    async def search(
        self,
        query: str,
        collection: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 20,
        offset: int = 0
    ) -> SearchResults:
        """
        Search documents using FTS5.
        
        Args:
            query: Search query (supports FTS5 syntax: "exact phrase", term1 AND term2, etc.)
            collection: Filter by collection
            tags: Filter by tags (all must match)
            limit: Maximum results
            offset: Pagination offset
        
        Returns:
            SearchResults with highlighted snippets
        """
        conn = self._get_connection()
        
        # Build query with filters
        where_clauses = ["fts_documents MATCH ?"]
        params = [query]
        
        join_clause = ""
        
        if collection:
            where_clauses.append("fts_documents.collection = ?")
            params.append(collection)
        
        if tags:
            # Filter by tags using doc_tags table
            tag_placeholders = ",".join(["?"] * len(tags))
            join_clause = f"""
                JOIN (
                    SELECT doc_id FROM doc_tags 
                    WHERE tag IN ({tag_placeholders}) 
                    GROUP BY doc_id 
                    HAVING COUNT(DISTINCT tag) = ?
                ) AS tag_filter ON fts_documents.doc_id = tag_filter.doc_id
            """
            params.extend(tags)
            params.append(len(tags))
        
        where_sql = " AND ".join(where_clauses)
        
        # Get total count
        count_sql = f"""
            SELECT COUNT(*) FROM fts_documents
            {join_clause}
            WHERE {where_sql}
        """
        total = conn.execute(count_sql, params).fetchone()[0]
        
        # Get results with highlighting
        # bm25() returns lower scores for better matches
        search_sql = f"""
            SELECT 
                fts_documents.doc_id,
                fts_documents.path,
                fts_documents.collection,
                fts_documents.title,
                fts_documents.content,
                bm25(fts_documents) as rank,
                snippet(fts_documents, 4, '<mark>', '</mark>', '...', 32) as snippet
            FROM fts_documents
            {join_clause}
            WHERE {where_sql}
            ORDER BY rank ASC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        
        rows = conn.execute(search_sql, params).fetchall()
        
        results = []
        for row in rows:
            results.append(SearchResult(
                doc_id=row["doc_id"],
                path=row["path"],
                collection=row["collection"],
                title=row["title"] or row["path"],
                content_snippet=row["snippet"] or row["content"][:200] + "...",
                highlights=row["snippet"] or "",
                rank=row["rank"],
                bm25_score=-row["rank"]  # Convert to positive score (higher = better)
            ))
        
        # Get facets
        facets = await self._get_facets(query, collection)
        
        # Log search
        conn.execute(
            "INSERT INTO search_history (query, results_count) VALUES (?, ?)",
            (query, total)
        )
        conn.commit()
        
        return SearchResults(
            query=query,
            total=total,
            results=results,
            facets=facets
        )
    
    async def _get_facets(self, query: str, project_filter: Optional[str] = None) -> dict:
        """Get faceted counts for search results."""
        conn = self._get_connection()
        
        facets = {
            "collections": {},
            "tags": {}
        }
        
        # Collection facet
        sql = """
            SELECT collection, COUNT(*) as count 
            FROM fts_documents 
            WHERE fts_documents MATCH ?
            GROUP BY collection
        """
        params = [query]
        
        if project_filter:
            sql = sql.replace("GROUP BY", "AND collection = ? GROUP BY")
            params.append(project_filter)
        
        for row in conn.execute(sql, params):
            facets["collections"][row["collection"]] = row["count"]
        
        # Tag facet
        tag_sql = """
            SELECT dt.tag, COUNT(*) as count
            FROM doc_tags dt
            JOIN fts_documents ft ON dt.doc_id = ft.doc_id
            WHERE ft.fts_documents MATCH ?
            GROUP BY dt.tag
            ORDER BY count DESC
            LIMIT 20
        """
        for row in conn.execute(tag_sql, [query]):
            facets["tags"][row["tag"]] = row["count"]
        
        return facets
    
    async def suggest(
        self,
        prefix: str,
        collection: Optional[str] = None,
        limit: int = 10
    ) -> list[dict]:
        """
        Get search suggestions based on prefix.
        
        Args:
            prefix: Search prefix
            collection: Filter by collection
            limit: Max suggestions
        
        Returns:
            List of suggestions with type (title, content, tag)
        """
        conn = self._get_connection()
        suggestions = []
        
        # Suggest from titles
        sql = "SELECT DISTINCT title, path FROM fts_documents WHERE title LIKE ? LIMIT ?"
        params = [f"%{prefix}%", limit]
        
        if collection:
            sql = sql.replace("WHERE", "WHERE collection = ? AND")
            params = [collection, f"%{prefix}%", limit]
        
        for row in conn.execute(sql, params):
            suggestions.append({
                "text": row["title"],
                "path": row["path"],
                "type": "title"
            })
        
        # Suggest from tags
        tag_sql = "SELECT DISTINCT tag FROM doc_tags WHERE tag LIKE ? LIMIT ?"
        for row in conn.execute(tag_sql, [f"%{prefix}%", limit - len(suggestions)]):
            suggestions.append({
                "text": row["tag"],
                "type": "tag"
            })
        
        return suggestions[:limit]
    
    async def get_stats(self) -> dict:
        """Get search index statistics."""
        conn = self._get_connection()
        
        stats = {
            "total_documents": 0,
            "total_terms": 0,
            "collections": [],
            "recent_searches": []
        }
        
        # Document count
        row = conn.execute("SELECT COUNT(*) FROM doc_metadata").fetchone()
        stats["total_documents"] = row[0]
        
        # Collection list
        for row in conn.execute("SELECT DISTINCT collection FROM doc_metadata ORDER BY collection"):
            stats["collections"].append(row["collection"])
        
        # Recent searches
        for row in conn.execute(
            "SELECT query, searched_at FROM search_history ORDER BY searched_at DESC LIMIT 10"
        ):
            stats["recent_searches"].append({
                "query": row["query"],
                "time": row["searched_at"]
            })
        
        return stats
    
    async def reindex_all(self, store_service) -> dict:
        """
        Reindex all documents from storage.
        
        Args:
            store_service: KnowledgeStoreService instance
        
        Returns:
            Statistics about reindexing
        """
        conn = self._get_connection()
        
        # Clear existing index
        conn.execute("DELETE FROM fts_documents")
        conn.execute("DELETE FROM doc_metadata")
        conn.execute("DELETE FROM doc_tags")
        conn.commit()
        
        # Get all documents
        documents = store_service.list_documents()
        
        indexed = 0
        failed = 0
        
        for doc in documents:
            try:
                # Read full content
                result = store_service.read_document(doc["path"])
                content = result.get("content", "")
                
                # Extract metadata
                title = doc.get("title", doc["path"].split("/")[-1])
                collection = doc["path"].split("/")[0] if "/" in doc["path"] else "default"
                
                # Index
                await self.index_document(
                    doc_id=doc["path"],
                    path=doc["path"],
                    title=title,
                    content=content,
                    collection=collection,
                    file_size=doc.get("size_bytes"),
                    word_count=len(content.split())
                )
                indexed += 1
                
            except Exception as e:
                logger.error(f"Failed to index {doc['path']}: {e}")
                failed += 1
        
        return {
            "indexed": indexed,
            "failed": failed,
            "total": len(documents)
        }
    
    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None


# Singleton instance
_fts_service: Optional[FTSService] = None


def get_fts_service() -> FTSService:
    """Get or create FTS service singleton."""
    global _fts_service
    if _fts_service is None:
        _fts_service = FTSService()
    return _fts_service
