from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class Document:
    content: str
    metadata: Dict[str, Any]
    id: Optional[str] = None
    embedding: Optional[List[float]] = None


@dataclass
class ExtractedEntity:
    name: str
    type: str
    full_name: str
    start_line: int
    end_line: int
    content: Optional[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class ExtractedRelation:
    source_full_name: str
    target_full_name: str
    relation_type: str
    start_line: Optional[int] = None


@dataclass
class ExtractionResult:
    documents: List[Document]
    entities: List[ExtractedEntity]
    relations: List[ExtractedRelation]


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
    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        ...

    @abstractmethod
    async def embed_query(self, query: str) -> List[float]:
        ...
