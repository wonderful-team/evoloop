"""
Core file outline extraction - Lightweight structural analysis.

This module provides basic file outline extraction using lightweight methods
(regex, simple parsing). For advanced language-specific parsing with TreeSitter,
use app.domain.codebase.indexing instead.
"""

import ast
import logging
import os
import re

from app.core.file.schemas import FilePreview, FileStats, OutlineEntry

from .io import detect_encoding

logger = logging.getLogger(__name__)

# Language-specific patterns for lightweight parsing
OUTLINE_PATTERNS = {
    "py": {
        "class": re.compile(r"^class\s+(\w+)"),
        "function": re.compile(r"^(?:async\s+)?def\s+(\w+)"),
    },
    "js": {
        "class": re.compile(r"^class\s+(\w+)"),
        "function": re.compile(r"^(?:async\s+)?(?:function\s+)?(\w+)\s*\("),
        "method": re.compile(r"^(\w+)\s*:\s*(?:async\s+)?\("),
    },
    "ts": {
        "class": re.compile(r"^class\s+(\w+)"),
        "interface": re.compile(r"^interface\s+(\w+)"),
        "function": re.compile(r"^(?:async\s+)?(?:function\s+)?(\w+)\s*[<(]"),
        "method": re.compile(r"^(\w+)\s*\??\s*:\s*(?:async\s+)?\("),
    },
    "go": {
        "function": re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)"),
        "struct": re.compile(r"^type\s+(\w+)\s+struct"),
        "interface": re.compile(r"^type\s+(\w+)\s+interface"),
    },
    "java": {
        "class": re.compile(r"^(?:public\s+|private\s+|protected\s+)?class\s+(\w+)"),
        "method": re.compile(r"^(?:public\s+|private\s+|protected\s+)?(?:static\s+)?\w+\s+(\w+)\s*\("),
    },
    "cpp": {
        "class": re.compile(r"^class\s+(\w+)"),
        "struct": re.compile(r"^struct\s+(\w+)"),
        "function": re.compile(r"^\w+\s+\*?\s*(\w+)\s*\([^)]*\)\s*\{"),
    },
    "h": {
        "class": re.compile(r"^class\s+(\w+)"),
        "struct": re.compile(r"^struct\s+(\w+)"),
        "function": re.compile(r"^\w+\s+\*?\s*(\w+)\s*\("),
    },
}


def get_file_outline(file_path: str, max_entries: int = 100) -> list[OutlineEntry]:
    """
    Extract structural outline from code files using lightweight parsing.

    This is a core-level function that uses regex and AST (for Python) to
    extract class/function definitions. For advanced TreeSitter-based parsing,
    use app.domain.codebase.indexing instead.

    Args:
        file_path: Path to the code file
        max_entries: Maximum number of outline entries to return

    Returns:
        List of outline entries with type, name, line, and indent
    """
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    outline = []

    try:
        # Python files: use AST for accuracy
        if ext == "py":
            return _get_python_outline_ast(file_path, max_entries)

        # Other languages: use regex patterns
        patterns = OUTLINE_PATTERNS.get(ext)
        if not patterns:
            return outline

        encoding = detect_encoding(file_path)
        with open(file_path, encoding=encoding) as f:
            for line_num, line in enumerate(f, 1):
                if len(outline) >= max_entries:
                    break

                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                    continue

                indent = len(line) - len(line.lstrip())

                for entry_type, pattern in patterns.items():
                    match = pattern.match(stripped)
                    if match:
                        name = match.group(1)
                        outline.append(
                            OutlineEntry(
                                type=entry_type,
                                name=name,
                                line=line_num,
                                indent=indent
                            )
                        )
                        break

    except Exception as e:
        logger.debug(f"Failed to extract outline from {file_path}: {e}")

    return outline


def _get_python_outline_ast(file_path: str, max_entries: int = 100) -> list[dict]:
    """
    Extract outline from Python file using AST (most accurate).

    Args:
        file_path: Path to Python file
        max_entries: Maximum entries to return

    Returns:
        List of outline entries
    """
    outline = []

    try:
        encoding = detect_encoding(file_path)
        with open(file_path, encoding=encoding) as f:
            source = f.read()

        tree = ast.parse(source)
        lines = source.split("\n")

        for node in ast.walk(tree):
            if len(outline) >= max_entries:
                break

            if isinstance(node, ast.ClassDef):
                line_num = node.lineno
                indent = _get_line_indent(lines, line_num)
                outline.append(
                    OutlineEntry(
                        type="class",
                        name=node.name,
                        line=line_num,
                        indent=indent
                    )
                )

                # Add methods
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and len(outline) < max_entries:
                        method_line = item.lineno
                        method_indent = _get_line_indent(lines, method_line)
                        outline.append(
                            OutlineEntry(
                                type="method",
                                name=item.name,
                                line=method_line,
                                indent=method_indent,
                            )
                        )

            elif isinstance(node, ast.FunctionDef) and not isinstance(
                node, ast.AsyncFunctionDef
            ):
                # Top-level function
                # Check if it's not a method (no parent class)
                if not any(
                    isinstance(parent, ast.ClassDef) for parent in ast.walk(tree)
                ):
                    line_num = node.lineno
                    indent = _get_line_indent(lines, line_num)
                    outline.append(
                        OutlineEntry(
                            type="function",
                            name=node.name,
                            line=line_num,
                            indent=indent,
                        )
                    )

            elif isinstance(node, ast.AsyncFunctionDef):
                line_num = node.lineno
                indent = _get_line_indent(lines, line_num)
                outline.append(
                    OutlineEntry(
                        type="function",
                        name=node.name,
                        line=line_num,
                        indent=indent
                    )
                )

        # Sort by line number
        outline.sort(key=lambda x: x["line"])

    except SyntaxError:
        # File has syntax errors
        pass
    except Exception as e:
        logger.debug(f"Failed to parse Python AST for {file_path}: {e}")

    return outline


def _get_line_indent(lines: list[str], line_num: int) -> int:
    """Get indentation level of a specific line."""
    if line_num < 1 or line_num > len(lines):
        return 0
    line = lines[line_num - 1]
    return len(line) - len(line.lstrip())


def get_large_file_preview(file_path: str, context_lines: int = 5, max_preview_lines: int = 100) -> FilePreview:
    """
    Get a preview of a large file with structural outline and sample content.

    This is a core-level function that provides intelligent preview for large files,
    showing the file structure (classes, functions) and relevant code sections.

    Args:
        file_path: Path to the file
        context_lines: Number of context lines around outline entries
        max_preview_lines: Maximum total lines in preview

    Returns:
        Dictionary with:
        - stats: File statistics (size, lines, encoding, hash)
        - outline: Structural outline
        - preview: Formatted preview content with line numbers
        - preview_lines: List of line numbers included in preview
    """
    from .io import get_file_info, read_file

    info = get_file_info(file_path)
    outline = get_file_outline(file_path)

    # Build set of lines to include in preview
    preview_line_numbers = set(range(1, min(context_lines + 1, info.total_lines + 1)))

    # Add context around outline entries
    for entry in outline[:20]:  # Top 20 outline items
        line = entry["line"]
        preview_line_numbers.update(range(
            max(1, line - context_lines),
            min(info.total_lines + 1, line + context_lines + 1)
        ))

    # Sort and limit preview lines
    sorted_lines = sorted(preview_line_numbers)
    if len(sorted_lines) > max_preview_lines:
        # Too fragmented, just take first N lines
        sorted_lines = list(range(1, min(max_preview_lines + 1, info.total_lines + 1)))

    # Build preview content with gaps indicated
    preview_content = ""
    last_printed = 0

    result = read_file(file_path, start_line=1, end_line=sorted_lines[-1] if sorted_lines else 1)
    if not result.success:
        return FilePreview(
            stats=FileStats(
                path=info.path,
                size=info.size,
                total_lines=info.total_lines,
                encoding=info.encoding,
                content_hash=info.content_hash,
            ),
            outline=outline,
            preview=f"[Error reading file: {result.error_message}]",
            preview_lines=[],
        )

    all_lines = result.content.split("\n")

    for line_num in sorted_lines:
        if line_num > len(all_lines):
            break

        # Detect gaps
        if last_printed and line_num > last_printed + 1:
            preview_content += f"     ... ({line_num - last_printed - 1} lines omitted) ...\n"

        line_content = all_lines[line_num - 1]
        preview_content += f"{line_num:4d}: {line_content}\n"
        last_printed = line_num

    return FilePreview(
        stats=FileStats(
            path=info.path,
            size=info.size,
            total_lines=info.total_lines,
            encoding=info.encoding,
            content_hash=info.content_hash,
        ),
        outline=outline,
        preview=preview_content,
        preview_lines=sorted_lines,
    )
