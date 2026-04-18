"""
Git-related Pydantic models for knowledge extraction and harvesting.
"""
from pydantic import Field

from app.core.memory.models import Concept
from app.infrastructure.pydantic_base import DynamicBaseModel


class GitConceptExtractionResult(DynamicBaseModel):
    """Result of extracting concepts from git diff."""
    concepts: list[Concept] = Field(description="List of extracted concepts")
