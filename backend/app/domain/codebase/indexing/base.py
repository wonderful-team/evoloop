from abc import ABC, abstractmethod

from app.domain.codebase.schemas import ExtractionResult


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
