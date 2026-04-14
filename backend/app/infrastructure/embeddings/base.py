from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from app.models.schemas.document import Document


class BaseEmbedder(ABC):
    """
    Abstract base class for generating embeddings.
    """

    @abstractmethod
    async def embed_documents(self, documents: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]: ...
