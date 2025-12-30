from typing import List

from openai import AsyncOpenAI

from app.core.config import settings
from app.domain.codebase.indexing.base import BaseEmbedder


class OpenAIEmbedder(BaseEmbedder):
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )
        self.model = settings.EMBEDDING_MODEL_NAME

    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        if not documents:
            return []
        # OpenAI batch size limit applies, should handle batching in production
        response = await self.client.embeddings.create(
            input=documents,
            model=self.model,
            dimensions=768
        )
        return [data.embedding for data in response.data]

    async def embed_query(self, query: str) -> List[float]:
        response = await self.client.embeddings.create(
            input=query,
            model=self.model,
            dimensions=768
        )
        return response.data[0].embedding
