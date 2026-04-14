from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.document import Document


class ExtractedEntity(DynamicBaseModel):
    name: str
    type: str
    full_name: str
    start_line: int
    end_line: int
    content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExtractedRelation(DynamicBaseModel):
    source_full_name: str
    target_full_name: str
    relation_type: str
    start_line: Optional[int] = None


class ExtractionResult(DynamicBaseModel):
    documents: List[Document] = Field(default_factory=list)
    entities: List[ExtractedEntity] = Field(default_factory=list)
    relations: List[ExtractedRelation] = Field(default_factory=list)


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
