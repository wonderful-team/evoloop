"""
Vector storage infrastructure for EvoLoop.
Uses LanceDB for client mode (embedded), pgvector for server mode.
"""

from app.core.config import settings

# Client mode: Always use LanceDB (embedded, no pgvector dependency)
# Server mode: Could use pgvector, but currently LanceDB is the primary store
from .lance_store import LanceVectorStore as VectorStore

__all__ = ["VectorStore"]
