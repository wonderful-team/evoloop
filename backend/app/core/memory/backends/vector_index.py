import logging
import os
from pathlib import Path
from typing import Any, List, Optional
import lancedb
import pyarrow as pa

from app.infrastructure.embeddings.factory import EmbedderFactory
from app.infrastructure.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)


class VectorMemoryIndex:
    """
    Vector index for semantic memory search using LanceDB.
    Uses the system's centralized EmbedderFactory for generating embeddings.
    """
    
    def __init__(self, db_path: Path, model_name: str | None = None):
        self.db_path = db_path
        self.model_name = model_name
        self._embedder: BaseEmbedder | None = None
        self._db: Any = None
        self._table: Any = None
        self._initialized = False
        self._dimensions: int | None = None

    @property
    def embedder(self) -> BaseEmbedder | None:
        if self._embedder is None:
            try:
                self._embedder = EmbedderFactory.get_embedder(self.model_name)
                if self._embedder:
                    logger.info(f"[VectorIndex] Initialized embedder: {type(self._embedder).__name__}")
                else:
                    logger.warning("[VectorIndex] No embedding provider configured. Semantic search will be disabled.")
            except Exception as e:
                logger.error(f"[VectorIndex] Failed to initialize embedder: {e}")
                return None
        return self._embedder

    async def initialize(self):
        """Initialize LanceDB and the memory table."""
        if self._initialized:
            return
            
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self.db_path))
        
        table_name = "memories"
        embedder = self.embedder
        
        if table_name not in self._db.table_names():
            if not embedder:
                logger.error("[VectorIndex] Cannot create table without an embedder.")
                return

            # Probe for dimensions if not explicitly known
            try:
                test_vector = await embedder.embed_query("probe")
                self._dimensions = len(test_vector)
                logger.info(f"[VectorIndex] Detected embedding dimensions: {self._dimensions}")
            except Exception as e:
                logger.error(f"[VectorIndex] Failed to probe dimensions: {e}")
                # Fallback to a common default if probe fails (e.g. 768 for Nomic)
                from app.core.config import settings
                self._dimensions = settings.EMBEDDING_DIMENSIONS or 768

            # Define schema: id, text (for embedding), metadata_json
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self._dimensions)),
                pa.field("text", pa.string()),
                pa.field("project_id", pa.int64()),
                pa.field("user_id", pa.string()),
            ])
            self._table = self._db.create_table(table_name, schema=schema)
            logger.info(f"[VectorIndex] Created new table '{table_name}' with dimensions {self._dimensions}")
        else:
            self._table = self._db.open_table(table_name)
            # Try to infer dimensions from existing table
            try:
                first_row = self._table.to_pandas().head(1)
                if not first_row.empty:
                    self._dimensions = len(first_row.iloc[0]['vector'])
                    logger.debug(f"[VectorIndex] Inferred dimensions from existing table: {self._dimensions}")
            except Exception:
                pass
            logger.info(f"[VectorIndex] Opened existing table '{table_name}'")
            
        self._initialized = True

    async def close(self) -> None:
        """Release resources."""
        self._db = None
        self._table = None
        self._initialized = False

    async def clear(self) -> None:
        """Clear all entries from the vector index."""
        if self._table is not None:
            try:
                self._table.delete("true")
            except Exception as e:
                logger.warning(f"[VectorIndex] Failed to clear table: {e}")
        self._initialized = False

    async def _get_embedding(self, text: str) -> List[float] | None:
        """Generate embedding for text."""
        embedder = self.embedder
        if embedder is None:
            logger.warning("[VectorIndex] No embedder available for embedding generation")
            return None
        try:
            return await embedder.embed_query(text)
        except Exception as e:
            logger.error(f"[VectorIndex] Embedding failed: {e}")
            return None

    async def add_entry(
        self, 
        memory_id: str, 
        text: str, 
        project_id: int | None = None, 
        user_id: str | None = None
    ):
        """Add or update an entry in the vector index."""
        if not self._initialized:
            await self.initialize()
            
        if self._table is None:
            return

        vector = await self._get_embedding(text)
        if vector is None or len(vector) == 0:
            logger.debug("[VectorIndex] Skipping vector update (embedder not available or zero-dim)")
            return

        data = [{
            "id": memory_id,
            "vector": vector,
            "text": text,
            "project_id": project_id if project_id is not None else -1,
            "user_id": user_id if user_id is not None else ""
        }]
        
        # LanceDB upsert is delete then add
        self._table.delete(f"id = '{memory_id}'")
        self._table.add(data)

    async def delete_entry(self, memory_id: str):
        """Remove an entry from the vector index."""
        if not self._initialized:
            await self.initialize()
        if self._table:
            self._table.delete(f"id = '{memory_id}'")

    async def search(self, query: str, filters: dict[str, Any] = None, limit: int = 10) -> List[dict]:
        """Search for relevant memories."""
        if not self._initialized:
            await self.initialize()
            
        if self._table is None:
            return []
            
        # Get query embedding
        query_vector = await self._get_embedding(query)
        
        if query_vector is None or len(query_vector) == 0:
            logger.debug("[VectorIndex] Skipping search (embedder not available or zero-dim)")
            return []
            
        # Build filter string for LanceDB
        where_clauses = []
        if filters:
            if "project_id" in filters and filters["project_id"] is not None:
                where_clauses.append(f"project_id = {filters['project_id']}")
            if "user_id" in filters and filters["user_id"] is not None:
                where_clauses.append(f"user_id = '{filters['user_id']}'")
        
        where_str = " AND ".join(where_clauses) if where_clauses else None
        
        # Search
        try:
            total_count = len(self._table)
            
            results = self._table.search(query_vector).limit(limit)
            if where_str:
                results = results.where(where_str)
                
            # Convert to list of dicts
            result_list = results.to_list()
            return result_list
        except Exception as e:
            logger.error(f"[VectorIndex] Search failed: {e}")
            return []
