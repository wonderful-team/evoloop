"""
Git-related Pydantic models for knowledge extraction and harvesting.
"""
from pydantic import BaseModel, Field


from app.infrastructure.pydantic_base import DynamicBaseModel


class Concept(DynamicBaseModel):
    """A knowledge concept extracted from git changes."""
    name: str = Field(description="Name of the concept, technology, or pattern")
    description: str = Field(description="Concise description of what it is and how it is used in this project")
    related_files: list[str] = Field(description="List of file paths related to this concept", default_factory=list)


class GitConceptExtractionResult(DynamicBaseModel):
    """Result of extracting concepts from git diff."""
    concepts: list[Concept] = Field(description="List of extracted concepts")
