"""
Git-related Pydantic models for knowledge extraction and harvesting.
"""
from pydantic import Field
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.core.memory.models import Concept


class GitConceptExtractionResult(DynamicBaseModel):
    """Result of extracting concepts from git diff."""
    concepts: list[Concept] = Field(description="List of extracted concepts")
