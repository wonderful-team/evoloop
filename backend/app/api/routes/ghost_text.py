"""
Ghost Text API Routes
=====================

Phase 4: Inline code completion suggestions (Ghost Text).

Provides intelligent code completions that can be displayed
inline in the editor as gray/ghost text.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.base import ScopedRequest

from app.core.ghost_text import EditPreview, GhostSuggestion, ghost_suggester

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ghost-text", tags=["ghost-text"])


# =============================================================================
# Request/Response Models
# =============================================================================

class InlineCompletionRequest(ScopedRequest):
    """Request for inline code completion."""
    file_path: str = Field(..., description="Path to the file being edited")
    cursor_line: int = Field(..., description="Current line number (1-indexed)", ge=1)
    cursor_column: int = Field(..., description="Current column position (0-indexed)", ge=0)
    current_line_text: str | None = Field(None, description="Text of current line up to cursor")
    context_lines: int = Field(10, description="Number of context lines to include", ge=0, le=50)
    project_id: int | None = Field(None, description="Project ID for context-aware suggestions")


class InlineCompletionResponse(BaseAPIResponse):
    """Response for inline completion request."""
    suggestion: GhostSuggestion | None = Field(None, description="Primary suggestion")
    alternative_suggestions: list[GhostSuggestion] = Field(default_factory=list, description="Alternative suggestions")


class EditPreviewRequest(ScopedRequest):
    """Request for edit preview as ghost text."""
    file_path: str = Field(..., description="Path to the file")
    edit_description: str = Field(..., description="Natural language description of the edit")
    cursor_line: int = Field(..., description="Current line number", ge=1)
    cursor_column: int = Field(..., description="Current column position", ge=0)
    project_id: int | None = Field(None, description="Project ID for context")


class EditPreviewResponse(BaseAPIResponse):
    """Response for edit preview request."""
    preview: EditPreview | None = Field(None, description="Edit preview data")


class GhostPatternItem(DynamicBaseModel):
    """Single ghost text pattern item."""
    pattern: str
    suggestion: str
    language: str
    description: str
    confidence: float


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/suggest", response_model=InlineCompletionResponse)
async def suggest_inline_completion(request: InlineCompletionRequest) -> InlineCompletionResponse:
    """
    Get inline code suggestions (Ghost Text) at cursor position.
    
    This endpoint provides intelligent code completions that can be displayed
    inline in the editor as gray/ghost text.
    
    Examples:
        - `def calc` → `ulate_sum(a, b):`
        - `class MyClass` → `:`
        - `for ` → `item in items:`
    
    Returns a suggestion with confidence score. Display as ghost text
    and accept on Tab key press.
    """
    try:
        # Read file content if exists
        file_content = ""
        try:
            from app.utils.file import safe_read_with_hash
            file_content, _, _ = safe_read_with_hash(request.file_path)
        except Exception:
            # File may not exist yet (new file)
            pass

        # Extract context around cursor
        lines = file_content.split('\n') if file_content else []
        context_start = max(0, request.cursor_line - 1 - request.context_lines)
        context_end = min(len(lines), request.cursor_line - 1 + request.context_lines)
        context = '\n'.join(lines[context_start:context_end])

        # Get current line content if not provided
        current_line = request.current_line_text or ""
        if not current_line and request.cursor_line <= len(lines):
            current_line = lines[request.cursor_line - 1][:request.cursor_column]

        # Get suggestion from suggester
        suggestion = await ghost_suggester.suggest_inline_completion(
            file_path=request.file_path,
            cursor_line=request.cursor_line,
            cursor_col=request.cursor_column,
            context_lines=request.context_lines,
            project_id=request.project_id,
        )

        if not suggestion:
            return InlineCompletionResponse(
                suggestion=None,
                alternative_suggestions=[]
            )

        # Convert to response model
        primary = GhostSuggestion(
            text=suggestion.text,
            confidence=suggestion.confidence,
            type=suggestion.type,
            source=suggestion.source,
            display_text=suggestion.display_text,
            description=suggestion.description,
        )

        # Generate alternative suggestions
        alternatives: list[GhostSuggestion] = []
        
        # Pattern-based alternatives for common cases
        if current_line.strip().startswith('def '):
            alt_text = current_line.strip()[4:]  # Remove 'def '
            if '(' not in alt_text:
                alternatives.append(GhostSuggestion(
                    text=f"({alt_text}_param):",
                    confidence=0.7,
                    type="completion",
                    source="pattern",
                    display_text=f"({alt_text}_param):",
                    description=f"Function with single param",
                ))
        
        if current_line.strip().startswith('class '):
            alt_text = current_line.strip()[6:]  # Remove 'class '
            if '(' not in alt_text:
                alternatives.append(GhostSuggestion(
                    text=f"(BaseClass):",
                    confidence=0.6,
                    type="completion",
                    source="pattern",
                    display_text=f"(BaseClass):",
                    description=f"Class with inheritance",
                ))

        return InlineCompletionResponse(
            suggestion=primary,
            alternative_suggestions=alternatives[:2],  # Max 2 alternatives
        )

    except Exception as e:
        logger.error(f"Failed to get inline completion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get suggestion: {str(e)}")


@router.post("/preview-edit", response_model=EditPreviewResponse)
async def preview_edit_ghost(request: EditPreviewRequest) -> EditPreviewResponse:
    """
    Preview what an edit would look like as Ghost Text.
    
    Takes a natural language description of an edit and returns
    a preview of the suggested changes.
    
    Example:
        - Description: "add docstring to this function"
        - Returns: Preview of the docstring to be added
    """
    try:
        # Read file content
        file_content = ""
        try:
            from app.utils.file import safe_read_with_hash
            file_content, _, _ = safe_read_with_hash(request.file_path)
        except Exception:
            pass

        # Get edit preview
        preview = await ghost_suggester.preview_edit(
            file_path=request.file_path,
            edit_description=request.edit_description,
            cursor_line=request.cursor_line,
            cursor_col=request.cursor_column,
            file_content=file_content,
            project_id=request.project_id,
        )

        if not preview:
            return EditPreviewResponse(preview=None)

        return EditPreviewResponse(preview=preview)

    except Exception as e:
        logger.error(f"Failed to get edit preview: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get preview: {str(e)}")


@router.get("/patterns", response_model=list[GhostPatternItem])
async def list_patterns(
    language: str | None = Query(None, description="Filter by language (py, ts, js, etc.)")
) -> list[GhostPatternItem]:
    """
    List available ghost text patterns.
    
    Returns all pattern-based suggestions that the system can provide.
    Useful for understanding what completions are available.
    """
    patterns = [
        # Python patterns
        GhostPatternItem(pattern="def <name>", suggestion="():", language="python", description="Function definition", confidence=0.9),
        GhostPatternItem(pattern="class <name>", suggestion=":", language="python", description="Class definition", confidence=0.95),
        GhostPatternItem(pattern="if", suggestion=" condition:", language="python", description="If statement", confidence=0.8),
        GhostPatternItem(pattern="elif", suggestion=" condition:", language="python", description="Elif statement", confidence=0.8),
        GhostPatternItem(pattern="else", suggestion=":", language="python", description="Else statement", confidence=0.95),
        GhostPatternItem(pattern="for", suggestion=" item in items:", language="python", description="For loop", confidence=0.8),
        GhostPatternItem(pattern="while", suggestion=" condition:", language="python", description="While loop", confidence=0.8),
        GhostPatternItem(pattern="try", suggestion=":", language="python", description="Try block", confidence=0.95),
        GhostPatternItem(pattern="except", suggestion=" <Exception>:", language="python", description="Except block", confidence=0.85),
        GhostPatternItem(pattern="finally", suggestion=":", language="python", description="Finally block", confidence=0.95),
        GhostPatternItem(pattern="with", suggestion=" context:", language="python", description="With statement", confidence=0.85),
        GhostPatternItem(pattern="from ", suggestion="module import ", language="python", description="From import", confidence=0.85),
        GhostPatternItem(pattern="import ", suggestion="module", language="python", description="Import statement", confidence=0.7),
        # TypeScript/JavaScript patterns
        GhostPatternItem(pattern="function ", suggestion="name() { }", language="typescript", description="Function declaration", confidence=0.85),
        GhostPatternItem(pattern="const ", suggestion="name = ", language="typescript", description="Const declaration", confidence=0.75),
        GhostPatternItem(pattern="if (", suggestion="condition) { }", language="typescript", description="If statement", confidence=0.85),
        GhostPatternItem(pattern="for (", suggestion="let i = 0; i < n; i++) { }", language="typescript", description="For loop", confidence=0.8),
    ]

    # Handle both direct calls and FastAPI Query parameter
    lang_value = None
    if language is not None:
        if isinstance(language, str):
            lang_value = language
        elif hasattr(language, 'default') and language.default is not None:
            # FastAPI Query object
            lang_value = str(language.default)
    
    if lang_value:
        lang_str = lang_value.lower()
        patterns = [p for p in patterns if p["language"] == lang_str]

    return patterns
