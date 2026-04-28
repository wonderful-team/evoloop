from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.document import Document
from app.domain.codebase.schemas import ExtractedEntity, ExtractedRelation, ExtractionResult


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
