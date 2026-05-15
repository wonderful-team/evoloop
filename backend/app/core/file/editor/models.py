from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class MatchConfidence(Enum):
    """Confidence level for text matching."""
    HIGH = "high"  # Exact match or very close
    MEDIUM = "medium"  # Fuzzy match successful
    LOW = "low"  # Multiple candidates or partial match
    NONE = "none"  # No match found


class EditPreviewResult(BaseModel):
    """Result of an edit preview operation."""
    success: bool
    confidence: MatchConfidence
    diff: str
    original_content: str
    new_content: str
    matched_text: Optional[str] = None
    strategy_used: Optional[str] = None
    message: Optional[str] = None


class FileEditOperation(BaseModel):
    """Single edit operation."""
    target: str = Field(..., description="The text to find and replace")
    replacement: str = Field(..., description="The new text")
    allow_multiple: bool = Field(False, description="Replace all occurrences of target")


class EditFileRequest(BaseModel):
    """Request for file editing."""
    path: str
    target: Optional[str] = None
    content: Optional[str] = None
    allow_multiple: bool = False
    expected_hash: Optional[str] = None
    verify_types: bool = True
    config: Optional[dict] = None
