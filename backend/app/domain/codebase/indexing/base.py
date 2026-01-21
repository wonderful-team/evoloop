from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Document:
    content: str
    metadata: dict[str, Any]
    id: str | None = None
    embedding: list[float] | None = None


@dataclass
class ExtractedEntity:
    name: str
    type: str
    full_name: str
    start_line: int
    end_line: int
    content: str | None = None
    metadata: dict[str, Any] = None


@dataclass
class ExtractedRelation:
    source_full_name: str
    target_full_name: str
    relation_type: str
    start_line: int | None = None


@dataclass
class ExtractionResult:
    documents: list[Document]
    entities: list[ExtractedEntity]
    relations: list[ExtractedRelation]


class BaseExtractor(ABC):
    """
    Abstract base class for extracting code structures (AST parsing).
    """

    @abstractmethod
    async def extract(self, file_path: str, content: str) -> ExtractionResult:
        """
        Parse code content and return structured extraction result.
        """
        ...


class BaseEmbedder(ABC):
    """
    Abstract base class for generating embeddings.
    """

    @abstractmethod
    async def embed_documents(self, documents: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]: ...
