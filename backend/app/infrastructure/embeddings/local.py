import logging
import asyncio
from typing import Any
from app.infrastructure.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)


class LocalEmbedder(BaseEmbedder):
    """
    Local implementation of BaseEmbedder using sentence-transformers.
    Ideal for EMBEDDED_MODE where no external API is available.
    
    Default: nomic-ai/nomic-embed-text-v1.5 (768 dimensions)
    Note: Nomic models require search_query: and search_document: prefixes.
    """

    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1.5", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._lock = asyncio.Lock()
        
        # Determine if we need Nomic-style prefixes
        self._is_nomic = "nomic" in model_name.lower()

    async def _get_model(self):
        async with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                logger.info(f"[LocalEmbedder] Loading model '{self.model_name}' on {self.device}...")
                # Nomic v1.5 requires trust_remote_code=True
                self._model = await asyncio.to_thread(
                    SentenceTransformer, 
                    self.model_name, 
                    device=self.device, 
                    trust_remote_code=True
                )
            return self._model

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []
        
        # Prepend prefix if using Nomic
        processed_docs = documents
        if self._is_nomic:
            processed_docs = [f"search_document: {doc}" if not doc.startswith("search_") else doc for doc in documents]
            
        model = await self._get_model()
        logger.debug(f"[LocalEmbedder] Embedding {len(documents)} documents...")
        embeddings = await asyncio.to_thread(model.encode, processed_docs, convert_to_numpy=True)
        return embeddings.tolist()

    async def embed_query(self, query: str) -> list[float]:
        if not query:
            return [0.0] * 768
            
        # Prepend prefix if using Nomic
        processed_query = query
        if self._is_nomic and not query.startswith("search_"):
            processed_query = f"search_query: {query}"
            
        model = await self._get_model()
        logger.debug(f"[LocalEmbedder] Embedding query: {query[:50]}...")
        embedding = await asyncio.to_thread(model.encode, processed_query, convert_to_numpy=True)
        return embedding.tolist()

    # LangChain-compatible aliases
    aembed_documents = embed_documents
    aembed_query = embed_query
