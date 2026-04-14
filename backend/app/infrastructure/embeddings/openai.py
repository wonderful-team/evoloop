import logging

from openai import AsyncOpenAI
from .base import BaseEmbedder

logger = logging.getLogger(__name__)


class GenericOpenAIEmbedder(BaseEmbedder):
    """
    Generic Embedder for any OpenAI-compatible API (OpenAI, LMStudio, vLLM, DeepSeek).
    """

    def __init__(self, api_key: str, base_url: str, model: str, dimensions: int = None):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        # Default dims usually kept None to let API decide, or specified if model requires
        self.dimensions = dimensions

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []

        # Prepare kwargs
        kwargs = {"input": documents, "model": self.model}
        if self.dimensions:
            kwargs["dimensions"] = self.dimensions

        try:
            response = await self.client.embeddings.create(**kwargs)
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"Embedding Error (Docs): {e}")
            raise e

    async def embed_query(self, query: str) -> list[float]:
        kwargs = {"input": query, "model": self.model}
        if self.dimensions:
            kwargs["dimensions"] = self.dimensions

        # DEBUG: Log embedding request details
        logger.info(f"Embedding Query Request: Model={self.model}, Dimensions={self.dimensions}, InputLength={len(query)}")

        try:
            response = await self.client.embeddings.create(**kwargs)
            if not response.data:
                raise ValueError(f"OpenAI returned empty data. Full Response: {response}")
            return response.data[0].embedding
        except Exception as e:
            # Log full stack if needed, but for now specific error message
            logger.error(f"Embedding Error (Query): {e}\nParams: {kwargs}")
            raise e

    # LangChain-compatible aliases
    aembed_documents = embed_documents
    aembed_query = embed_query


OpenAIEmbedder = GenericOpenAIEmbedder
