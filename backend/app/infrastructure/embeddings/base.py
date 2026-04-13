from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Any

from app.utils.model_helpers import LegacyDictMixin


class Document(BaseModel, LegacyDictMixin):
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None
    embedding: list[float] | None = None


class BaseEmbedder(ABC):
    """
    Abstract base class for generating embeddings.
    """

    @abstractmethod
    async def embed_documents(self, documents: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]: ...
