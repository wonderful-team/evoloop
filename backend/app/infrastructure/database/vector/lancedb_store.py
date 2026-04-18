"""
LanceDB vector storage implementation for EvoLoop Backend (Embedded Mode).
Replaces PostgreSQL + pgvector with embedded file-based storage.
"""

import hashlib
from pathlib import Path
from typing import Any, Optional

import lancedb
import pyarrow as pa

from app.core.config import settings
from app.logging import logger


class LanceVectorStore:
    """
    LanceDB-based vector storage for local client mode.

    Tables:
        - code_chunks: Code embeddings with metadata
        - doc_chunks: Document embeddings
        - symbol_index: Symbol search index
    """

    _instance: Optional["LanceVectorStore"] = None

    def __new__(cls, db_path: str | None = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str | None = None):
        if self._initialized:
            return

        self.db_path = Path(db_path or settings.LANCEDB_PATH)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.client = lancedb.connect(str(self.db_path))

        # Initialize tables
        self._init_tables()
        self._initialized = True

        logger.info(f"[LanceVectorStore] Initialized at {self.db_path}")

    def _init_tables(self):
        """Initialize LanceDB tables if not exist."""
        # Code chunks table
        try:
            self.code_table = self.client.open_table("code_chunks")
            logger.debug("[LanceVectorStore] Opened existing code_chunks table")
        except Exception: # Handle multiple possible exception types (FileNotFoundError, ValueError)
            self.code_table = self._create_code_chunks_table()
            logger.info("[LanceVectorStore] Created code_chunks table")

        # Document chunks table
        try:
            self.doc_table = self.client.open_table("doc_chunks")
        except Exception:
            self.doc_table = self._create_doc_chunks_table()

        # Symbol index table
        try:
            self.symbol_table = self.client.open_table("symbol_index")
        except Exception:
            self.symbol_table = self._create_symbol_table()

    def _create_code_chunks_table(self):
        """Create code chunks table with schema."""
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), settings.EMBEDDING_DIMENSIONS)),
            pa.field("content", pa.string()),
            pa.field("file_path", pa.string()),
            pa.field("repository_id", pa.string()),
            pa.field("chunk_type", pa.string()),  # function, class, module
            pa.field("identifier", pa.string()),   # function name, class name
            pa.field("start_line", pa.int32()),
            pa.field("end_line", pa.int32()),
            pa.field("language", pa.string()),
            pa.field("checksum", pa.string()),     # content hash for dedup
            pa.field("created_at", pa.timestamp("ms")),
        ])
        return self.client.create_table("code_chunks", schema=schema)

    def _create_doc_chunks_table(self):
        """Create document chunks table."""
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), settings.EMBEDDING_DIMENSIONS)),
            pa.field("content", pa.string()),
            pa.field("source_type", pa.string()),  # wiki, note, external
            pa.field("source_id", pa.string()),
            pa.field("title", pa.string()),
            pa.field("chunk_index", pa.int32()),
            pa.field("created_at", pa.timestamp("ms")),
        ])
        return self.client.create_table("doc_chunks", schema=schema)

    def _create_symbol_table(self):
        """Create symbol index table for fast symbol lookup."""
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), settings.EMBEDDING_DIMENSIONS)),
            pa.field("name", pa.string()),
            pa.field("full_name", pa.string()),
            pa.field("symbol_type", pa.string()),  # class, function, variable
            pa.field("file_path", pa.string()),
            pa.field("repository_id", pa.string()),
            pa.field("language", pa.string()),
            pa.field("line_number", pa.int32()),
            pa.field("created_at", pa.timestamp("ms")),
        ])
        return self.client.create_table("symbol_index", schema=schema)

    def upsert_code_chunks(
        self,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]]
    ) -> int:
        """
        Upsert code chunks with embeddings.

        Args:
            chunks: List of chunk metadata dicts
            embeddings: List of embedding vectors

        Returns:
            Number of chunks inserted
        """
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have same length")

        if not chunks:
            return 0

        from datetime import datetime

        # Generate IDs from content hash
        ids = [
            hashlib.md5(f"{c['file_path']}:{c['start_line']}:{c['content'][:100]}".encode()).hexdigest()
            for c in chunks
        ]

        table_data = pa.table({
            "id": ids,
            "vector": embeddings,
            "content": [c["content"] for c in chunks],
            "file_path": [c["file_path"] for c in chunks],
            "repository_id": [c.get("repository_id", "") for c in chunks],
            "chunk_type": [c.get("chunk_type", "unknown") for c in chunks],
            "identifier": [c.get("identifier", "") for c in chunks],
            "start_line": [c.get("start_line", 0) for c in chunks],
            "end_line": [c.get("end_line", 0) for c in chunks],
            "language": [c.get("language", "unknown") for c in chunks],
            "checksum": [hashlib.md5(c["content"].encode()).hexdigest()[:16] for c in chunks],
            "created_at": [datetime.utcnow() for _ in chunks],
        })

        # Merge insert: update if exists, insert if new
        self.code_table.merge_insert("id") \
            .when_matched_update_all() \
            .when_not_matched_insert_all() \
            .execute(table_data)

        logger.debug(f"[LanceVectorStore] Upserted {len(chunks)} code chunks")
        return len(chunks)

    def search_code(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: str | None = None,
        repository_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Semantic search for code chunks.

        Args:
            query_vector: Query embedding vector
            top_k: Number of results
            filters: LanceDB filter expression
            repository_id: Optional repository filter

        Returns:
            List of matching chunks with scores
        """
        # Build query
        query = self.code_table.search(query_vector)

        # Apply filters
        if repository_id:
            repo_filter = f"repository_id = '{repository_id}'"
            filters = f"({filters}) AND {repo_filter}" if filters else repo_filter

        if filters:
            query = query.where(filters)

        # Execute search
        results = query.limit(top_k).to_list()

        # Format output
        return [
            {
                "id": r["id"],
                "content": r["content"],
                "file_path": r["file_path"],
                "repository_id": r["repository_id"],
                "chunk_type": r["chunk_type"],
                "identifier": r["identifier"],
                "start_line": r["start_line"],
                "end_line": r["end_line"],
                "language": r["language"],
                "score": 1.0 - r["_distance"],  # Convert distance to similarity
            }
            for r in results
        ]

    def full_text_search_code(
        self,
        query_text: str,
        top_k: int = 10
    ) -> list[dict[str, Any]]:
        """
        Full-text search on code content.
        Requires LanceDB FTS index.
        """
        try:
            results = self.code_table.search(query_text, query_type="fts").limit(top_k).to_list()
            return [
                {
                    "id": r["id"],
                    "content": r["content"],
                    "file_path": r["file_path"],
                    "identifier": r["identifier"],
                    "score": r.get("_score", 0),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"[LanceVectorStore] FTS search failed: {e}, falling back to content filter")
            # Fallback: simple string matching
            return self._fallback_text_search(query_text, top_k)

    def _fallback_text_search(self, query_text: str, top_k: int) -> list[dict[str, Any]]:
        """Fallback text search using simple filtering."""
        # This is a naive implementation - in production, use proper FTS
        all_data = self.code_table.to_pandas()
        matches = all_data[all_data["content"].str.contains(query_text, case=False, na=False)]
        matches = matches.head(top_k)

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "file_path": row["file_path"],
                "identifier": row["identifier"],
                "score": 1.0,  # No scoring in fallback
            }
            for _, row in matches.iterrows()
        ]

    def delete_by_repository(self, repository_id: str) -> int:
        """Delete all chunks for a repository."""
        # LanceDB doesn't support delete yet in some versions
        # Workaround: mark as deleted or filter in queries
        # For now, return 0 and filter in queries
        logger.warning(f"[LanceVectorStore] Delete not implemented, filtering repo {repository_id}")
        return 0

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        return {
            "db_path": str(self.db_path),
            "code_chunks": self.code_table.count_rows(),
            "doc_chunks": self.doc_table.count_rows(),
            "symbols": self.symbol_table.count_rows(),
            "embedding_dim": settings.EMBEDDING_DIMENSIONS,
        }

    def compact(self):
        """Compact database files."""
        self.code_table.compact_files()
        self.doc_table.compact_files()
        self.symbol_table.compact_files()
        logger.info("[LanceVectorStore] Database compacted")


# Global instance for easy access
vector_store: LanceVectorStore | None = None


def get_vector_store() -> LanceVectorStore:
    """Get or create global vector store instance."""
    global vector_store
    if vector_store is None:
        vector_store = LanceVectorStore()
    return vector_store
