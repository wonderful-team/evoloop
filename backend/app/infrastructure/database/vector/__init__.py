"""Vector storage backends for EvoLoop."""

import logging
from typing import Optional

from app.core.config import settings
from app.infrastructure.database.vector.base import BaseVectorStore

logger = logging.getLogger(__name__)

_vector_store: Optional[BaseVectorStore] = None


def get_vector_store() -> BaseVectorStore:
    """Get the global vector store instance (lazy singleton).

    Returns:
        BaseVectorStore: LanceVectorStore in embedded mode, PgVectorStore otherwise.
    """
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    if settings.EMBEDDED_MODE:
        from app.infrastructure.database.vector.lancedb_store import LanceVectorStore

        _vector_store = LanceVectorStore()
        logger.info("[VectorStore] Initialized LanceVectorStore (embedded mode)")
    else:
        from app.infrastructure.database.vector.pgvector_store import PgVectorStore

        _vector_store = PgVectorStore()
        logger.info("[VectorStore] Initialized PgVectorStore (production mode)")

    return _vector_store


def reset_vector_store() -> None:
    """Reset the global vector store instance (useful for testing)."""
    global _vector_store
    _vector_store = None
    logger.debug("[VectorStore] Vector store reset")


__all__ = ["BaseVectorStore", "get_vector_store", "reset_vector_store"]
