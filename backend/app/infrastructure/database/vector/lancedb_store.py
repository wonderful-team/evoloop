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
from app.infrastructure.database.vector.base import BaseVectorStore
from app.logging import logger
from app.utils.time import utcnow
from datetime import datetime


class LanceVectorStore(BaseVectorStore):
    """
    LanceDB-based vector storage for local client mode.

    Tables:
        - code_chunks: Code embeddings with metadata
        - doc_chunks: Document embeddings
        - kb_chunks: Knowledge base chunks
        - memories: Semantic memory embeddings
        - skills: Learned skill embeddings
        - concepts: Graph concept embeddings
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

        # Knowledge base chunks table (T-3.1)
        try:
            self.kb_table = self.client.open_table("kb_chunks")
        except Exception:
            self.kb_table = self._create_kb_chunks_table()


        # Memories table
        try:
            self.memory_table = self.client.open_table("memories")
        except Exception:
            self.memory_table = self._create_memories_table()
        # Skills table
        try:
            self.skills_table = self.client.open_table("skills")
        except Exception:
            self.skills_table = self._create_skills_table()

        # Concepts table
        try:
            self.concepts_table = self.client.open_table("concepts")
        except Exception:
            self.concepts_table = self._create_concepts_table()

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
            pa.field("created_at", pa.timestamp("us")),
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

    def _create_kb_chunks_table(self):
        """Create knowledge base chunks table with collection support (T-3.1)."""
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), settings.EMBEDDING_DIMENSIONS)),
            pa.field("content", pa.string()),
            pa.field("source_type", pa.string()),
            pa.field("source_id", pa.string()),
            pa.field("title", pa.string()),
            pa.field("chunk_index", pa.int32()),
            pa.field("collection", pa.string()),
            pa.field("tags", pa.string()),
            pa.field("created_at", pa.timestamp("ms")),
        ])
        return self.client.create_table("kb_chunks", schema=schema)

    def _create_memories_table(self):
        """Create memories table with schema."""
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), settings.EMBEDDING_DIMENSIONS)),
            pa.field("text", pa.string()),
            pa.field("project_id", pa.int32()),
            pa.field("user_id", pa.string()),
            pa.field("created_at", pa.timestamp("us")),
        ])
        return self.client.create_table("memories", schema=schema)

    def _create_skills_table(self):
        """Create skills table with schema."""
        schema = pa.schema([
            pa.field("id", pa.string()), # skill name or uuid
            pa.field("vector", pa.list_(pa.float32(), settings.EMBEDDING_DIMENSIONS)),
            pa.field("name", pa.string()),
            pa.field("description", pa.string()),
            pa.field("bundle_id", pa.string()), # For Atlas: App identifier
            pa.field("platform", pa.string()),  # For Atlas: android/macos
            pa.field("x", pa.int32()),           # For Atlas: Spatial coordinate
            pa.field("y", pa.int32()),           # For Atlas: Spatial coordinate
            pa.field("state_id", pa.string()),   # For Atlas: UI state context
            pa.field("label", pa.string()),      # For Atlas: UI element label
            pa.field("created_at", pa.timestamp("us")),
        ])
        return self.client.create_table("skills", schema=schema)

    def _create_concepts_table(self):
        """Create concepts table with schema."""
        schema = pa.schema([
            pa.field("id", pa.string()), # concept id
            pa.field("vector", pa.list_(pa.float32(), settings.EMBEDDING_DIMENSIONS)),
            pa.field("name", pa.string()),
            pa.field("description", pa.string()),
            pa.field("project_id", pa.int32()),
            pa.field("created_at", pa.timestamp("us")),
        ])
        return self.client.create_table("concepts", schema=schema)

    def upsert_code_chunks(
        self,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]]
    ) -> int:
        """
        Upsert code chunks with embeddings.

        Uses delete-then-add to avoid LanceDB merge_insert concurrency issues.
        """
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have same length")

        if not chunks:
            return 0

        #    (avoids LanceDB merge_insert concurrency bugs)
        file_paths = {c["file_path"] for c in chunks}
        for fp in file_paths:
            try:
                safe_fp = fp.replace("'", "''")
                self.code_table.delete(f"file_path = '{safe_fp}'")
            except Exception:
                pass

        # 2. Generate IDs from content hash
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
            "created_at": [utcnow() for _ in chunks],
        })

        self.code_table.add(table_data)
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
        try:
            self.code_table.delete(f"repository_id = '{repository_id.replace(chr(39), chr(39)+chr(39))}'")
            logger.info(f"[LanceVectorStore] Deleted chunks for repo {repository_id}")
            return 1
        except Exception as e:
            logger.warning(f"[LanceVectorStore] Failed to delete repo {repository_id}: {e}")
            return 0

    def upsert_kb_chunks(self, records: list[dict[str, Any]]) -> int:
        """Upsert knowledge base chunk records (T-3.1).

        Deletes existing chunks for affected doc_ids then inserts fresh records
        to avoid LanceDB merge_insert compatibility issues.
        """
        if not records:
            return 0

        # Delete existing chunks for these doc_ids first
        doc_ids = {r["source_id"] for r in records}
        for doc_id in doc_ids:
            try:
                # Use parameterized-style filtering to avoid injection
                self.kb_table.delete(f"source_id = '" + doc_id.replace("'", "''") + "'")
            except Exception:
                pass

        # Ensure datetime precision matches schema (ms, no microseconds)
        now = utcnow().replace(microsecond=0)
        table_data = pa.table({
            "id": [r["id"] for r in records],
            "vector": [r["vector"] for r in records],
            "content": [r["content"] for r in records],
            "source_type": [r.get("source_type", "kb") for r in records],
            "source_id": [r["source_id"] for r in records],
            "title": [r.get("title", "") for r in records],
            "chunk_index": [r.get("chunk_index", 0) for r in records],
            "collection": [r.get("collection", "default") for r in records],
            "tags": [r.get("tags", "") for r in records],
            "created_at": [r.get("created_at", now).replace(microsecond=0) for r in records],
        })

        self.kb_table.add(table_data)
        logger.debug(f"[LanceVectorStore] Upserted {len(records)} KB chunks")
        return len(records)

    def search_kb(
        self,
        query_vector: list[float],
        top_k: int = 10,
        collection: str | None = None
    ) -> list[dict[str, Any]]:
        """Semantic search over knowledge base chunks (T-3.1)."""
        query = self.kb_table.search(query_vector)

        if collection:
            # Sanitize collection to prevent filter injection
            safe_collection = collection.replace("'", "''").replace("\"", "\"\"")
            query = query.where(f"collection = '{safe_collection}'")

        results = query.limit(top_k).to_list()

        return [
            {
                "id": r["id"],
                "content": r["content"],
                "doc_id": r["source_id"],
                "title": r["title"],
                "collection": r["collection"],
                "score": 1.0 - r["_distance"],
            }
            for r in results
        ]

    def delete_kb_by_doc(self, doc_id: str) -> int:
        """Delete all chunks for a given document (T-3.1)."""
        try:
            self.kb_table.delete(f"source_id = '{doc_id}'")
            return 1
        except Exception as e:
            logger.warning(f"[LanceVectorStore] KB delete failed: {e}")
            return 0

    # -- memories -----------------------------------------------------------

    def upsert_memory_chunks(self, records: list[dict[str, Any]]) -> int:
        """Upsert memory chunk records."""
        if not records:
            return 0

        now = utcnow().replace(microsecond=0)

        # Delete existing memories for these IDs first
        ids = {r["id"] for r in records}
        for mid in ids:
            self.memory_table.delete(f"id = '{mid.replace(chr(39), chr(39)+chr(39))}'")

        table_data = pa.table({
            "id": [r["id"] for r in records],
            "vector": [r["vector"] for r in records],
            "text": [r.get("text", "") or r.get("content", "") for r in records],
            "project_id": [r.get("project_id") if r.get("project_id") is not None else -1 for r in records],
            "user_id": [r.get("user_id", "") for r in records],
            "created_at": [r.get("created_at", now).replace(microsecond=0) for r in records],
        })

        self.memory_table.add(table_data)
        logger.debug(f"[LanceVectorStore] Upserted {len(records)} memory chunks")
        return len(records)

    def search_memory(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Semantic search over memory chunks."""
        query = self.memory_table.search(query_vector)

        if filters:
            where_clauses = []
            if "project_id" in filters and filters["project_id"] is not None:
                where_clauses.append(f"project_id = {filters['project_id']}")
            if "user_id" in filters and filters["user_id"] is not None:
                where_clauses.append(f"user_id = '{filters['user_id']}'")
            
            if where_clauses:
                query = query.where(" AND ".join(where_clauses))

        results = query.limit(top_k).to_list()

        return [
            {
                "id": r["id"],
                "text": r["text"],
                "project_id": r["project_id"],
                "user_id": r["user_id"],
                "score": 1.0 - r["_distance"],
            }
            for r in results
        ]

    def delete_memory_by_id(self, memory_id: str) -> bool:
        """Remove a specific memory entry by its ID."""
        try:
            self.memory_table.delete(f"id = '{memory_id.replace(chr(39), chr(39)+chr(39))}'")
            return True
        except Exception as e:
            logger.warning(f"[LanceVectorStore] Memory delete failed for {memory_id}: {e}")
            return False

    def delete_all_memories(self) -> int:
        """Wipe all memory entries."""
        try:
            count = self.memory_table.count_rows()
            self.memory_table.delete("true")
            return count
        except Exception as e:
            logger.warning(f"[LanceVectorStore] Failed to clear memories: {e}")
            return 0

    # -- skills -----------------------------------------------------------

    def upsert_skill_chunks(self, records: list[dict[str, Any]]) -> int:
        """Upsert skill chunk records."""
        now = utcnow()

        table_data = pa.Table.from_pydict({
            "id": [r["id"] for r in records],
            "vector": [r["vector"] for r in records],
            "name": [r.get("name", "") for r in records],
            "description": [r.get("description", "") for r in records],
            "bundle_id": [r.get("bundle_id", "") for r in records],
            "platform": [r.get("platform", "android") for r in records],
            "x": [r.get("x", -1) for r in records],
            "y": [r.get("y", -1) for r in records],
            "state_id": [r.get("state_id", "") for r in records],
            "label": [r.get("label", "") for r in records],
            "created_at": [r.get("created_at", now).replace(microsecond=0) for r in records],
        })

        self.skills_table.add(table_data)
        return len(records)

    def search_skills(self, query_vector: list[float], bundle_id: str | None = None, platform: str | None = None, top_k: int = 10) -> list[dict[str, Any]]:
        """Semantic search over learned skills with Atlas filtering."""
        query = self.skills_table.search(query_vector)
        
        filters = []
        if bundle_id:
            filters.append(f"bundle_id = '{bundle_id}'")
        if platform:
            filters.append(f"platform = '{platform}'")
        
        if filters:
            query = query.where(" AND ".join(filters))
            
        results = query.limit(top_k).to_list()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "bundle_id": r.get("bundle_id"),
                "platform": r.get("platform"),
                "x": r.get("x"),
                "y": r.get("y"),
                "state_id": r.get("state_id"),
                "label": r.get("label"),
                "score": 1.0 - r["_distance"],
            }
            for r in results
        ]

    # -- concepts ---------------------------------------------------------

    def upsert_concept_chunks(self, records: list[dict[str, Any]]) -> int:
        """Upsert concept records."""
        now = utcnow()

        table_data = pa.Table.from_pydict({
            "id": [r["id"] for r in records],
            "vector": [r["vector"] for r in records],
            "name": [r.get("name", "") for r in records],
            "description": [r.get("description", "") for r in records],
            "project_id": [r.get("project_id", -1) for r in records],
            "created_at": [r.get("created_at", now).replace(microsecond=0) for r in records],
        })

        self.concepts_table.add(table_data)
        return len(records)

    def search_concepts(self, query_vector: list[float], top_k: int = 10) -> list[dict[str, Any]]:
        """Semantic search over graph concepts."""
        results = self.concepts_table.search(query_vector).limit(top_k).to_list()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "score": 1.0 - r["_distance"],
            }
            for r in results
        ]

    # -- maintenance --------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        return {
            "db_path": str(self.db_path),
            "code_chunks": self.code_table.count_rows(),
            "doc_chunks": self.doc_table.count_rows(),
            "kb_chunks": self.kb_table.count_rows(),
            "memories": self.memory_table.count_rows(),
            "skills": self.skills_table.count_rows(),
            "concepts": self.concepts_table.count_rows(),
            "embedding_dim": settings.EMBEDDING_DIMENSIONS,
        }

    def compact(self):
        """Compact database files."""
        self.code_table.compact_files()
        self.doc_table.compact_files()
        self.memory_table.compact_files()
        self.skills_table.compact_files()
        self.concepts_table.compact_files()
        logger.info("[LanceVectorStore] Database compacted")

    def truncate_all(self) -> None:
        """Wipe all data from all LanceDB tables."""
        for table_name in ["code_chunks", "doc_chunks", "kb_chunks", "memories", "skills", "concepts"]:
            try:
                table = self.client.open_table(table_name)
                table.delete("true")
            except Exception as e:
                logger.warning(f"[LanceVectorStore] Failed to truncate {table_name}: {e}")
        logger.info("[LanceVectorStore] All tables truncated")
