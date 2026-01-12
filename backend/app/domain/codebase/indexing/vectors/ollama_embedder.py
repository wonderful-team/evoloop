
import httpx

from app.domain.codebase.indexing.base import BaseEmbedder


import logging

logger = logging.getLogger(__name__)

class OllamaEmbedder(BaseEmbedder):
    """
    Native Ollama Embedder using /api/embeddings endpoint.
    Reference: https://github.com/ollama/ollama/blob/main/docs/api.md#generate-embeddings
    """
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.model = model

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []

        # Ollama /api/embeddings is single-vector only as of standard API?
        # Checking docs: /api/embed (new) supports batch?
        # Let's check recent Ollama versions. /api/embed is the new efficient endpoint.

        results = []
        async with httpx.AsyncClient() as client:
             # Try batch endpoint if available, but for safety iterate or use mbed
             # Using /api/embeddings (legacy) or /api/embed

             # Implementation for /api/embeddings (one by one, reliable)
             for doc in documents:
                 res = await self._embed_one(client, doc)
                 results.append(res)
        return results

    async def embed_query(self, query: str) -> list[float]:
        async with httpx.AsyncClient() as client:
            return await self._embed_one(client, query)

    async def _embed_one(self, client: httpx.AsyncClient, text: str) -> list[float]:
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text
        }
        try:
            response = await client.post(url, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            return data["embedding"]
        except Exception as e:
            # Fallback for newer /api/embed API?
            # Or handle error
            logger.error(f"Ollama Embedding Error: {e}")
            raise e
