import logging
import os
from pathlib import Path
from typing import Any, List, Optional
import lancedb
import pyarrow as pa
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class VectorMemoryIndex:
    """
    Vector index for semantic memory search using LanceDB.
    """
    
    def __init__(self, db_path: Path, model_name: str = "all-MiniLM-L6-v2"):
        self.db_path = db_path
        self.model_name = model_name
        self._model = None
        self._db = None
        self._table = None
        self._initialized = False

    @property
    def model(self):
        if self._model is None:
            logger.info(f"[VectorIndex] Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    async def initialize(self):
        """Initialize LanceDB and the memory table."""
        if self._initialized:
            return
            
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self.db_path))
        
        table_name = "memories"
        if table_name not in self._db.table_names():
            # Define schema: id, text (for embedding), metadata_json
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), 384)), # MiniLM dimension is 384
                pa.field("text", pa.string()),
                pa.field("project_id", pa.int64()),
                pa.field("user_id", pa.string()),
            ])
            self._table = self._db.create_table(table_name, schema=schema)
            logger.info(f"[VectorIndex] Created new table '{table_name}'")
        else:
            self._table = self._db.open_table(table_name)
            logger.info(f"[VectorIndex] Opened existing table '{table_name}'")
            
        self._initialized = True

    def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        return self.model.encode(text).tolist()

    async def add_entry(self, memory_id: str, text: str, project_id: int | None, user_id: str | None):
        """Add or update an entry in the vector index."""
        if not self._initialized:
            await self.initialize()
            
        vector = self._get_embedding(text)
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
        self._table.delete(f"id = '{memory_id}'")

    async def search(self, query: str, filters: dict = None, limit: int = 10) -> List[dict]:
        """
        Perform semantic search.
        filters can include project_id and user_id.
        """
        if not self._initialized:
            await self.initialize()
            
        query_vector = self._get_embedding(query)
        
        # Build filter string for LanceDB
        where_clauses = []
        if filters:
            if "project_id" in filters and filters["project_id"] is not None:
                where_clauses.append(f"project_id = {filters['project_id']}")
            if "user_id" in filters and filters["user_id"] is not None:
                where_clauses.append(f"user_id = '{filters['user_id']}'")
        
        where_str = " AND ".join(where_clauses) if where_clauses else None
        
        # Search
        results = self._table.search(query_vector).limit(limit)
        if where_str:
            results = results.where(where_str)
            
        # Convert to list of dicts
        return results.to_list()

    async def clear(self):
        """Clear all entries."""
        if self._initialized:
            self._db.drop_table("memories")
            self._initialized = False
            await self.initialize()

    async def close(self):
        """Close connection."""
        self._db = None
        self._table = None
        self._initialized = False
