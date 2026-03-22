"""
Preview Edit Tool
=================

Preview code changes before applying them.
Generates a diff view and confidence score without modifying the file.
"""

from typing import Annotated
from dataclasses import dataclass
from enum import Enum

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool
from app.utils.file import safe_read_with_hash


class MatchConfidence(Enum):
    """Confidence level for text matching."""
    HIGH = "high"      # Exact match or very close
    MEDIUM = "medium"  # Fuzzy match successful
    LOW = "low"        # Multiple candidates or partial match
    NONE = "none"      # No match found


@dataclass
class EditPreviewResult:
    """Result of previewing an edit."""
    success: bool
    confidence: MatchConfidence
    diff: str
    original_content: str
    new_content: str
    matched_text: str | None
    strategy_used: str | None
    message: str


def generate_unified_diff(
    original: str,
    modified: str,
    file_path: str = "file",
    context_lines: int = 3
) -> str:
    """
    Generate unified diff format.
    
    Args:
        original: Original file content
        modified: Modified file content
        file_path: File path for diff header
        context_lines: Number of context lines around changes
    
    Returns:
        Unified diff string
    """
    import difflib
    
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    
    # Ensure lines end with newline for proper diff
    if original_lines and not original_lines[-1].endswith('\n'):
        original_lines[-1] += '\n'
    if modified_lines and not modified_lines[-1].endswith('\n'):
        modified_lines[-1] += '\n'
    
    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines
    )
    
    return ''.join(diff)


def calculate_confidence(
    strategy_name: str,
    is_exact_match: bool,
    match_count: int,
    similarity_score: float = 1.0
) -> MatchConfidence:
    """
    Calculate confidence level based on matching strategy and results.
    
    Args:
        strategy_name: Name of the strategy used
        is_exact_match: Whether it's an exact match
        match_count: Number of matches found
        similarity_score: Fuzzy similarity score (0-1)
    
    Returns:
        Confidence level
    """
    if is_exact_match and match_count == 1:
        return MatchConfidence.HIGH
    
    if match_count > 1:
        return MatchConfidence.LOW
    
    if strategy_name == "simple_replacer":
        return MatchConfidence.HIGH
    
    if similarity_score >= 0.8:
        return MatchConfidence.HIGH
    elif similarity_score >= 0.5:
        return MatchConfidence.MEDIUM
    else:
        return MatchConfidence.LOW


async def preview_edit_internal(
    path: str,
    target: str,
    replacement: str,
    config: RunnableConfig | None = None
) -> EditPreviewResult:
    """
    Internal function to preview edit without applying changes.
    
    Args:
        path: File path
        target: Text to find
        replacement: Replacement text
        config: RunnableConfig
    
    Returns:
        EditPreviewResult with diff and confidence
    """
    from .actions.utils import resolve_and_validate_path
    from app.domain.tools.utils.editing.engine import EditEngine
    
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return EditPreviewResult(
            success=False,
            confidence=MatchConfidence.NONE,
            diff="",
            original_content="",
            new_content="",
            matched_text=None,
            strategy_used=None,
            message=f"Path error: {e}"
        )
    
    # Read file content
    try:
        file_content, encoding, stats = safe_read_with_hash(target_path)
    except Exception as e:
        return EditPreviewResult(
            success=False,
            confidence=MatchConfidence.NONE,
            diff="",
            original_content="",
            new_content="",
            matched_text=None,
            strategy_used=None,
            message=f"Failed to read file: {e}"
        )
    
    if not file_content:
        return EditPreviewResult(
            success=False,
            confidence=MatchConfidence.NONE,
            diff="",
            original_content="",
            new_content="",
            matched_text=None,
            strategy_used=None,
            message="File is empty"
        )
    
    # Try to apply replacement using EditEngine
    success, new_content, log = EditEngine.apply_replacement(
        content=file_content,
        old_string=target,
        new_string=replacement,
        replace_all=False
    )
    
    if not success:
        return EditPreviewResult(
            success=False,
            confidence=MatchConfidence.NONE,
            diff="",
            original_content=file_content,
            new_content="",
            matched_text=None,
            strategy_used=None,
            message=f"Could not find target text. {log}"
        )
    
    # Extract strategy name from log
    strategy_used = None
    if "strategy:" in log.lower():
        strategy_used = log.split(":")[-1].strip()
    
    # Check if exact match
    is_exact = target in file_content
    match_count = file_content.count(target) if is_exact else 1
    
    # Calculate confidence
    confidence = calculate_confidence(
        strategy_name=strategy_used or "unknown",
        is_exact_match=is_exact,
        match_count=match_count
    )
    
    # Generate diff
    diff = generate_unified_diff(
        original=file_content,
        modified=new_content,
        file_path=path
    )
    
    return EditPreviewResult(
        success=True,
        confidence=confidence,
        diff=diff,
        original_content=file_content,
        new_content=new_content,
        matched_text=target if is_exact else None,
        strategy_used=strategy_used,
        message=log
    )


@evoloop_tool(
    is_pollable=True,
    is_state_mutating=False,  # Preview does not modify
    summary_template="database_logger.tool_summary.preview_edit",
    affected_path_keys=["path"],
    name_map={"zh": "预览编辑", "en": "Preview Edit"}
)
async def preview_edit(
    path: str | None = None,
    target: str | None = None,
    replacement: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Preview code changes before applying them. Shows a diff and confidence score.
    
    This tool helps you see exactly what will change before committing to an edit.
    Use this when:
    - You're unsure if the target text will match correctly
    - You want to review changes before applying
    - The edit might have multiple matches and you need to verify
    
    Args:
        path: Target file path. **REQUIRED**
        target: The exact text to find. **REQUIRED**
        replacement: The new content. **REQUIRED**
    
    Returns:
        A preview of the changes including:
        - Confidence level (high/medium/low)
        - Unified diff showing changes
        - Matching strategy used
        - Whether the change is safe to apply
    
    Example:
        preview_edit(
            path="src/main.py",
            target="def old_function():",
            replacement="def new_function():"
        )
    """
    # Validation
    if not path:
        return "Error: 'path' is required."
    if target is None:
        return "Error: 'target' is required."
    if replacement is None:
        return "Error: 'replacement' is required."
    
    result = await preview_edit_internal(path, target, replacement, config)
    
    if not result.success:
        from app.utils import render_template
        return render_template("report/response.prompt.j2", success=False, message="Preview failed", details=result.message, note="Try providing more context around the target text.")
    
    # Format output
    # Format output using render_template
    from app.utils import render_template
    
    details_lines = [
        f"Strategy: {result.strategy_used or 'unknown'}",
        result.message,
        "",
        "--- Preview Diff ---",
        "```diff",
        result.diff if result.diff else "(No changes detected)",
        "```"
    ]
    
    if result.confidence == MatchConfidence.LOW:
        details_lines.insert(0, "⚠️ Warning: Low confidence match. Please review carefully before applying.")
    # Metadata construction removed
    # Cleanup: Hardcoded message removed

    # Hint for the final response
    hint = (
        f"To apply this change, use:\n"
        f"   edit_file(path='{path}', target='''{target[:50]}{'...' if len(target) > 50 else ''}''', replacement='''{replacement[:50]}{'...' if len(replacement) > 50 else ''}''')"
    )
    
    # Output building removed, replaced by render_template below
    
    # Action hint logic moved up
    
    return render_template(
        "report/response.prompt.j2",
        success=True,
        message=f"Edit Preview ({result.confidence.value.upper()})",
        details="\n".join(details_lines),
        note=hint
    )
