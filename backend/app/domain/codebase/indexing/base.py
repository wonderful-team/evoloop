from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Document:
    content: str
    metadata: Dict[str, Any]
    id: Optional[str] = None
    embedding: Optional[List[float]] = None


class BaseExtractor(ABC):
    """
    Abstract base class for extracting code structures (AST parsing).
    """

    @abstractmethod
    async def extract(self, file_path: str, content: str) -> List[Document]:
        """
        Parse code content and return list of Documents (chunks).
        """
        ...


class BaseEmbedder(ABC):
    """
    Abstract base class for generating embeddings.
    """

    @abstractmethod
    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        ...

    @abstractmethod
    async def embed_query(self, query: str) -> List[float]:
        ...
