from enum import Enum

from pydantic import BaseModel, Field


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
    matched_text: str | None = None
    strategy_used: str | None = None
    message: str | None = None


class FileEditOperation(BaseModel):
    """Single edit operation."""

    target: str = Field(
        "",
        description="The text to find and replace. Leave empty when mode=append/prepend.",
    )
    replacement: str = Field(
        ..., description="The new text or content to append/prepend"
    )
    allow_multiple: bool = Field(False, description="Replace all occurrences of target")
    mode: str = Field(
        "replace",
        description="'replace' (default), 'append' (add to end of file), 'prepend' (add to beginning)",
    )
    start_line: int | None = Field(
        None, description="Optional 1-indexed starting line number constraint"
    )
    end_line: int | None = Field(
        None, description="Optional 1-indexed ending line number constraint (inclusive)"
    )


class EditFileRequest(BaseModel):
    """Request for file editing."""

    path: str
    target: str | None = None
    content: str | None = None
    allow_multiple: bool = False
    mode: str = "replace"
    start_line: int | None = None
    end_line: int | None = None
    expected_hash: str | None = None
    verify_types: bool = True
    config: dict | None = None
