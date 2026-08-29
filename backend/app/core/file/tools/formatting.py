"""File content formatting utilities for agent-facing display.

Methods in this module turn project file contents (source code, documents,
spreadsheets) into prompt-ready strings without leaking presentation details
into the file reading logic.
"""

from app.utils.detect import detect_language
from app.utils.template import render_template


def format_file_content(filename: str, content: str, lang: str = None, has_header: bool = False) -> str:
    """Format file content with optional syntax highlighting.

    Args:
        filename: Name of the file (used for language auto-detection).
        content: Raw file content.
        lang: Optional language hint; detected from filename if omitted.
        has_header: Whether the file content already includes a header.

    Returns:
        Rendered string using the domain/project/file_content.prompt.j2 template.
    """
    if not lang and filename:
        lang = detect_language(filename)

    return render_template(
        "domain/project/file_content.prompt.j2",
        filename=filename,
        content=content,
        lang=lang or "text",
        has_header=has_header,
    )


def format_spreadsheet(filename: str, sheets: list) -> str:
    """Format spreadsheet content with multiple sheets.

    Args:
        filename: Name of the spreadsheet file.
        sheets: List of sheet descriptors.

    Returns:
        Rendered string using the domain/project/spreadsheet_content.prompt.j2 template.
    """
    return render_template(
        "domain/project/spreadsheet_content.prompt.j2",
        filename=filename,
        sheets=sheets,
    )
