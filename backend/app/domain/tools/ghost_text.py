"""
Ghost Text Support
==================

Provides inline code suggestions (Ghost Text) for IDE integration.

Note: These functions are NOT exposed as Agent tools.
They are used internally by API routes for IDE/editor integration.

For Agent file editing, use:
- edit_file(path, target, replacement, dry_run=True) for preview
- edit_file(path, target, replacement) for actual edit
"""

from app.core.ghost_text.suggester import suggest_ghost_text, ghost_suggester


async def _resolve_and_validate_path(file_path: str) -> str | None:
    """
    Resolve and validate file path for IDE integration.
    Ensures the file is within the working directory.
    """
    from app.domain.tools.files.utils import resolve_and_validate_path
    try:
        return await resolve_and_validate_path(file_path, None)
    except ValueError:
        return None


async def suggest_inline_completion(
    file_path: str,
    cursor_line: int,
    cursor_column: int,
    current_line_text: str | None = None,
) -> str:
    """
    Get inline code suggestions (Ghost Text) at cursor position.
    
    This function provides intelligent code completions for IDE integration.
    It is NOT an Agent tool - use edit_file() for Agent file editing.
    
    Args:
        file_path: Path to the file being edited (must be within working directory)
        cursor_line: Current line number (1-indexed)
        cursor_column: Current column position (0-indexed)
        current_line_text: Text of current line up to cursor (optional)
    
    Returns:
        JSON with suggestion text, confidence, and metadata
    """
    import json
    
    if not file_path or cursor_line < 1 or cursor_column < 0:
        return json.dumps({"error": "Invalid parameters"})
    
    # Validate path is within working directory
    validated_path = await _resolve_and_validate_path(file_path)
    if not validated_path:
        return json.dumps({"error": "File path is outside the working directory"})
    
    # Auto-detect current line text if not provided
    if current_line_text is None:
        try:
            with open(validated_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if cursor_line <= len(lines):
                    current_line_text = lines[cursor_line - 1][:cursor_column]
        except Exception:
            pass
    
    result = await suggest_ghost_text(
        file_path=file_path,
        cursor_line=cursor_line,
        cursor_column=cursor_column,
        current_line_text=current_line_text or ""
    )
    
    if result:
        return json.dumps(result, indent=2)
    
    return json.dumps({"suggestion": None})


async def preview_edit_ghost(
    file_path: str,
    edit_description: str,
    cursor_line: int,
    cursor_column: int,
) -> str:
    """
    Preview what an edit would look like as Ghost Text.
    
    This function is for IDE integration.
    It is NOT an Agent tool - use edit_file(dry_run=True) for Agent preview.
    
    Args:
        file_path: Path to the file (must be within working directory)
        edit_description: Natural language description (e.g., "add docstring")
        cursor_line: Current line number
        cursor_column: Current column position
    
    Returns:
        JSON with suggested edit preview
    """
    import json
    
    # Validate path is within working directory
    validated_path = await _resolve_and_validate_path(file_path)
    if not validated_path:
        return json.dumps({"error": "File path is outside the working directory"})
    
    try:
        with open(validated_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        position = sum(len(line) for line in lines[:cursor_line-1]) + cursor_column
        
        suggestion = await ghost_suggester.suggest_edit_preview(
            file_path=validated_path,
            edit_description=edit_description,
            cursor_position=position
        )
        
        if suggestion:
            return json.dumps(suggestion.to_dict(), indent=2)
        
        return json.dumps({"suggestion": None, "message": "No preview available"})
        
    except Exception as e:
        return json.dumps({"error": str(e)})
