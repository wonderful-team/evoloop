"""Vector storage backends for EvoLoop."""

from app.core.config import settings

# Export based on configuration
if settings.EMBEDDED_MODE:
    from .lancedb_store import LanceVectorStore, get_vector_store

    __all__ = ["LanceVectorStore", "get_vector_store"]
else:
    # In non-embedded mode, PostgreSQL vector operations are in models
    __all__ = []
