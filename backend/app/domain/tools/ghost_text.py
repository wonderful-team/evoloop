"""
Ghost Text Tool
===============

Provides inline code suggestions (Ghost Text) for enhanced editing experience.
"""

from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool
from app.core.ghost_text.suggester import suggest_ghost_text, ghost_suggester


@evoloop_tool(
    is_pollable=True,
    is_state_mutating=False,
    summary_template="database_logger.tool_summary.ghost_text",
    name_map={"zh": "获取代码建议", "en": "Suggest Ghost Text"}
)
async def suggest_inline_completion(
    file_path: str,
    cursor_line: int,
    cursor_column: int,
    current_line_text: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Get inline code suggestions (Ghost Text) at cursor position.
    
    This tool provides intelligent code completions that can be displayed
    inline in the editor as gray/ghost text.
    
    Args:
        file_path: Path to the file being edited
        cursor_line: Current line number (1-indexed)
        cursor_column: Current column position (0-indexed)
        current_line_text: Text of current line up to cursor (optional)
    
    Returns:
        JSON with suggestion text, confidence, and metadata
    
    Example:
        suggest_inline_completion(
            file_path="src/main.py",
            cursor_line=10,
            cursor_column=8,
            current_line_text="def calc"
        )
        # Returns: {"text": "ulate_sum(a, b):", "confidence": 0.9, ...}
    """
    import json
    
    if not file_path or cursor_line < 1 or cursor_column < 0:
        return json.dumps({"error": "Invalid parameters"})
    
    # Auto-detect current line text if not provided
    if current_line_text is None:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
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


@evoloop_tool(
    is_pollable=True,
    is_state_mutating=False,
    summary_template="database_logger.tool_summary.edit_preview",
    name_map={"zh": "预览编辑建议", "en": "Preview Edit Suggestion"}
)
async def preview_edit_ghost(
    file_path: str,
    edit_description: str,
    cursor_line: int,
    cursor_column: int,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Preview what an edit would look like as Ghost Text.
    
    Args:
        file_path: Path to the file
        edit_description: Natural language description (e.g., "add docstring")
        cursor_line: Current line number
        cursor_column: Current column position
    
    Returns:
        JSON with suggested edit preview
    
    Example:
        preview_edit_ghost(
            file_path="src/main.py",
            edit_description="add docstring to this function",
            cursor_line=10,
            cursor_column=0
        )
    """
    import json
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        position = sum(len(line) for line in lines[:cursor_line-1]) + cursor_column
        
        suggestion = await ghost_suggester.suggest_edit_preview(
            file_path=file_path,
            edit_description=edit_description,
            cursor_position=position
        )
        
        if suggestion:
            return json.dumps(suggestion.to_dict(), indent=2)
        
        return json.dumps({"suggestion": None, "message": "No preview available"})
        
    except Exception as e:
        return json.dumps({"error": str(e)})
