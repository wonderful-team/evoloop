import logging
from typing import Any, List

from app.infrastructure.database.vector import get_vector_store
from app.infrastructure.embeddings.factory import EmbedderFactory
from app.infrastructure.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)


class VectorMemoryIndex:
    """
    Adapter for semantic memory search using the unified VectorStore architecture.
    Delegates storage to LanceVectorStore (embedded) or PgVectorStore (production).
    """
    
    def __init__(self, db_path: Any = None, model_name: str | None = None):
        # db_path is preserved for backward compatibility but ignored as the 
        # unified vector store manages its own paths.
        self.model_name = model_name
        self._embedder: BaseEmbedder | None = None
        self._initialized = False
        self._vector_store = get_vector_store()

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
        """Initialize the unified vector store."""
        if self._initialized:
            return
        
        # BaseVectorStore implementations handle their own table initialization.
        self._initialized = True
        logger.info("[VectorIndex] Adapter initialized using unified VectorStore.")

    async def close(self) -> None:
        """Release resources."""
        self._initialized = False

    async def clear(self) -> None:
        """Clear all entries from the memory vector index."""
        logger.info("[VectorIndex] Clearing all memory entries via unified VectorStore.")
        self._vector_store.delete_all_memories()

    async def _get_embedding(self, text: str) -> List[float] | None:
        """Generate embedding for text."""
        embedder = self.embedder
        if embedder is None:
            logger.warning("[VectorIndex] No embedder available for embedding generation")
            return None

        return await embedder.embed_query(text)

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

        vector = await self._get_embedding(text)
        if vector is None or len(vector) == 0:
            logger.debug("[VectorIndex] Skipping vector update (embedder not available or zero-dim)")
            return

        record = {
            "id": memory_id,
            "vector": vector,
            "text": text,
            "project_id": project_id,
            "user_id": user_id or ""
        }
        self._vector_store.upsert_memory_chunks([record])

    async def delete_entry(self, memory_id: str):
        """Remove an entry from the vector index."""
        if not self._initialized:
            await self.initialize()
        self._vector_store.delete_memory_by_id(memory_id)

    async def search(self, query: str, filters: dict[str, Any] = None, limit: int = 10) -> List[dict]:
        """Search for relevant memories."""
        if not self._initialized:
            await self.initialize()
            
        # Get query embedding
        query_vector = await self._get_embedding(query)
        
        if query_vector is None or len(query_vector) == 0:
            logger.debug("[VectorIndex] Skipping search (embedder not available or zero-dim)")
            return []
            
        results = self._vector_store.search_memory(
            query_vector=query_vector,
            top_k=limit,
            filters=filters
        )
        
        return results
