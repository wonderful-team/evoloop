"""Schemas for tools module."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.core.engine.message.native_classes import RunnableConfig
from app.infrastructure.pydantic_base import DynamicBaseModel


class MatchConfidence(Enum):
    """Confidence level for text matching."""

    HIGH = "high"  # Exact match or very close
    MEDIUM = "medium"  # Fuzzy match successful
    LOW = "low"  # Multiple candidates or partial match
    NONE = "none"  # No match found


class DocxHeading(BaseModel):
    style: str
    text: str


class ExcelSheetInfo(DynamicBaseModel):
    columns: list[str]
    preview: list[dict]


class ExcelInspectionResult(DynamicBaseModel):
    sheets: list[str]
    details: dict[str, ExcelSheetInfo]


class DocxInspectionResult(DynamicBaseModel):
    headings_count: int
    headings: list[DocxHeading]


class PdfInspectionResult(DynamicBaseModel):
    pages: int
    metadata: dict | None = None


class CreatePythonToolInput(BaseModel):
    name: str = Field(..., description="The name of the tool (snake_case), e.g., 'calculate_hash'.")
    description: str = Field(..., description="A clear description of what the tool does and its arguments.")
    code: str = Field(..., description="The Python code defining the function. MUST include type hints and a docstring.")
    version: str | None = Field("1.0.0", description="Version string.")


class FileEditOperation(BaseModel):
    """Single edit operation within a multi-edit request."""

    target: str
    replacement: str
    allow_multiple: bool = False
    mode: str | None = "replace"
    start_line: int | None = None
    end_line: int | None = None


class EditFileRequest(BaseModel):
    """Request model for editing a file."""

    path: str
    target: str | None = None
    content: str | None = None
    allow_multiple: bool = False
    expected_hash: str | None = None
    verify_types: bool = True
    config: RunnableConfig | None = None
    edits: list[FileEditOperation] | None = None
    mode: str | None = "replace"
    start_line: int | None = None
    end_line: int | None = None


class EditPreviewResult(BaseModel):
    """Result of previewing an edit."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    confidence: MatchConfidence
    diff: str
    original_content: str
    new_content: str
    matched_text: str | None = None
    strategy_used: str | None = None
    message: str


class ExtractedConcept(BaseModel):
    name: str = Field(description="Name of the concept, technology, or pattern")
    description: str = Field(description="Concise description of the concept")


class SearchNativeToolsSchema(BaseModel):
    query: str = Field(
        "",
        description="Optional keyword to filter tools by name or description. Leave empty to list all available execution tools.",
    )


class SearchSkillsSchema(BaseModel):
    query: str = Field(
        "",
        description="The specific action or pattern you are looking to perform. e.g. 'click on save button'",
    )
    namespace: str = Field(
        None,
        description="Optional directory tree namespace to restrict the search. e.g. 'android', 'macos', 'browser'",
    )
    index_mode: bool = Field(
        False,
        description="If True, returns a high-level catalog of all skills in the namespace instead of searching for a specific match.",
    )


class GetWorkspaceTreeSchema(BaseModel):
    dir_path: str = Field(".", description="Subdirectory to list. If omitted, lists from the current working directory root.")
    max_depth: int = Field(2, description="Maximum depth of the directory tree to explore.")
    with_symbols: bool = Field(False, description="Whether to include code symbols (classes/functions) in the tree. Defaults to False for speed and token economy.")
