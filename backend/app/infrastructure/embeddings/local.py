import logging
import asyncio
from typing import Any
from app.infrastructure.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)

class LocalEmbedder(BaseEmbedder):
    """
    Local implementation of BaseEmbedder using sentence-transformers.
    Ideal for EMBEDDED_MODE where no external API is available.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._lock = asyncio.Lock()

    async def _get_model(self):
        async with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                logger.info(f"[LocalEmbedder] Loading model '{self.model_name}' on {self.device}...")
                # Use to_thread to avoid blocking event loop during model load
                self._model = await asyncio.to_thread(SentenceTransformer, self.model_name, device=self.device)
            return self._model

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []
        model = await self._get_model()
        logger.debug(f"[LocalEmbedder] Embedding {len(documents)} documents...")
        embeddings = await asyncio.to_thread(model.encode, documents, convert_to_numpy=True)
        return embeddings.tolist()

    async def embed_query(self, query: str) -> list[float]:
        if not query:
            return [0.0] * 768
        model = await self._get_model()
        logger.debug(f"[LocalEmbedder] Embedding query: {query[:50]}...")
        embedding = await asyncio.to_thread(model.encode, query, convert_to_numpy=True)
        return embedding.tolist()
