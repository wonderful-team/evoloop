import logging
from app.infrastructure.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)

class NoOpEmbedder(BaseEmbedder):
    """
    Null Object implementation of BaseEmbedder.
    Used when no embedding provider is configured to prevent crashes
    while providing clear logging.
    """

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        logger.debug("[NoOpEmbedder] embed_documents called but no provider is configured. Returning empty list.")
        return []

    async def embed_query(self, query: str) -> list[float]:
        logger.warning("[NoOpEmbedder] embed_query called but no provider is configured. Search results may be incomplete.")
        return []
