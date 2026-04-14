"""
Ghost Text Suggester
====================

Provides inline code suggestions (Ghost Text) for editor integration.
"""

import logging
from typing import TYPE_CHECKING, Optional

from pydantic import Field

from app.domain.codebase.indexing.parsers import parser_registry
from app.infrastructure.pydantic_base import DynamicBaseModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class GhostSuggestion(DynamicBaseModel):
    """A ghost text suggestion for inline display."""
    text: str = Field(..., description="The suggested text to insert")
    trigger_position: int = Field(..., description="Position where the suggestion was triggered")
    confidence: float = Field(..., description="Confidence score (0-1)", ge=0, le=1)
    source: str = Field(..., description="Source: pattern, llm, context")
    type: str = Field("completion", description="Suggestion type: completion, edit_preview, snippet")
    description: Optional[str] = Field(None, description="Tooltip description")
    display_text: Optional[str] = Field(None, description="Formatted display text")


class EditPreview(DynamicBaseModel):
    """An edit preview showing original and suggested text."""
    original_text: str = Field(..., description="The original text before edit")
    suggested_text: str = Field(..., description="The suggested text after edit")
    description: str = Field(..., description="Description of the change")
    line_start: int = Field(..., description="Starting line of the edit", ge=1)
    line_end: int = Field(..., description="Ending line of the edit", ge=1)


class GhostTextSuggester:
    """Generates inline code suggestions (Ghost Text)."""
    
    def __init__(self):
        self._cache = {}
    
    async def suggest_inline_completion(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        context_lines: int = 10,
        project_id: int | None = None
    ) -> GhostSuggestion | None:
        """
        Suggest code completion at cursor position (API-friendly version).
        
        Args:
            file_path: Path to the file being edited
            cursor_line: Current line number (1-indexed)
            cursor_col: Current column position (0-indexed)
            context_lines: Number of context lines to include
            project_id: Optional project ID for context-aware suggestions
        
        Returns:
            GhostSuggestion or None if no suggestion available
        """
        try:
            # Read file content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except FileNotFoundError:
                content = ""
            except Exception as e:
                logger.warning(f"Could not read file {file_path}: {e}")
                content = ""
            
            lines = content.split('\n')
            current_line_num = cursor_line - 1  # Convert to 0-indexed
            
            if current_line_num < 0 or current_line_num >= len(lines):
                return None
            
            current_line = lines[current_line_num][:cursor_col]
            
            start_line = max(0, current_line_num - context_lines)
            end_line = min(len(lines), current_line_num + context_lines + 1)
            context = '\n'.join(lines[start_line:end_line])
            
            suggestion = self._pattern_based_suggestion(
                current_line, context, file_path
            )
            
            if suggestion:
                return suggestion
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to generate inline completion: {e}")
            return None
    
    async def suggest_completion(
        self,
        file_path: str,
        cursor_position: int,
        current_line: str,
        context_lines: int = 5
    ) -> GhostSuggestion | None:
        """Suggest code completion at cursor position."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            current_line_num = content[:cursor_position].count('\n')
            
            start_line = max(0, current_line_num - context_lines)
            end_line = min(len(lines), current_line_num + context_lines + 1)
            context = '\n'.join(lines[start_line:end_line])
            
            suggestion = self._pattern_based_suggestion(
                current_line, context, file_path
            )
            
            if suggestion:
                return suggestion
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to generate suggestion: {e}")
            return None
    
    async def suggest_edit_preview(
        self,
        file_path: str,
        edit_description: str,
        cursor_position: int
    ) -> GhostSuggestion | None:
        """Preview what an edit would look like."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            ext = file_path.split('.')[-1] if '.' in file_path else ''
            parser_info = parser_registry.get_parser(ext)
            
            if parser_info:
                parser, language = parser_info
                tree = parser.parse(bytes(content, 'utf8'))
                
                cursor_node = self._get_node_at_position(tree.root_node, cursor_position)
                
                if cursor_node:
                    suggestion = self._generate_contextual_suggestion(
                        cursor_node, edit_description
                    )
                    if suggestion:
                        return suggestion
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to generate edit preview: {e}")
            return None
    
    async def preview_edit(
        self,
        file_path: str,
        edit_description: str,
        cursor_line: int,
        cursor_col: int,
        file_content: str | None = None,
        project_id: int | None = None
    ) -> EditPreview | None:
        """
        Preview what an edit would look like.
        
        Args:
            file_path: Path to the file
            edit_description: Natural language description of the edit
            cursor_line: Current line number (1-indexed)
            cursor_col: Current column position (0-indexed)
            file_content: Optional file content (if already read)
            project_id: Optional project ID for context
        
        Returns:
            EditPreview or None if preview cannot be generated
        """
        try:
            # Read file if content not provided
            if file_content is None:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                except FileNotFoundError:
                    return None
            
            lines = file_content.split('\n')
            current_line_num = cursor_line - 1  # Convert to 0-indexed
            
            if current_line_num < 0 or current_line_num >= len(lines):
                return None
            
            current_line = lines[current_line_num]
            
            # Simple edit preview based on description
            desc_lower = edit_description.lower()
            
            # Docstring preview
            if "docstring" in desc_lower or "document" in desc_lower:
                # Find function definition
                for i in range(current_line_num, -1, -1):
                    if lines[i].strip().startswith('def '):
                        func_line = lines[i].strip()
                        func_name = func_line[4:].split('(')[0].strip()
                        
                        indent = len(lines[i]) - len(lines[i].lstrip())
                        doc_indent = " " * (indent + 4)
                        
                        suggested_doc = f'\n{doc_indent}"""\n{doc_indent}{func_name} description.\n{doc_indent}\n{doc_indent}Args:\n{doc_indent}    TBD\n{doc_indent}\n{doc_indent}Returns:\n{doc_indent}    TBD\n{doc_indent}"""'
                        
                        return EditPreview(
                            original_text="",
                            suggested_text=suggested_doc,
                            description=f"Add docstring for {func_name}",
                            line_start=i + 1,
                            line_end=i + 1
                        )
            
            # Type hint preview
            if "type" in desc_lower or "hint" in desc_lower:
                if 'def ' in current_line:
                    return EditPreview(
                        original_text="",
                        suggested_text=" -> ReturnType",
                        description="Add return type hint",
                        line_start=cursor_line,
                        line_end=cursor_line
                    )
            
            # Import preview
            if "import" in desc_lower:
                return EditPreview(
                    original_text="",
                    suggested_text="from typing import Optional, List, Dict\n",
                    description="Add common imports",
                    line_start=1,
                    line_end=1
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to generate edit preview: {e}")
            return None
    
    def _pattern_based_suggestion(
        self,
        current_line: str,
        context: str,
        file_path: str
    ) -> GhostSuggestion | None:
        """Generate suggestion based on common code patterns."""
        
        # Function definition patterns
        if current_line.strip().startswith('def ') and not current_line.endswith(':'):
            func_name = current_line.strip()[4:].strip()
            if '(' not in func_name:
                return GhostSuggestion(
                    text="():",
                    trigger_position=len(current_line),
                    confidence=0.9,
                    source="pattern",
                    description="Function definition"
                )
        
        # Class definition
        if current_line.strip().startswith('class ') and not current_line.endswith(':'):
            return GhostSuggestion(
                text=":",
                trigger_position=len(current_line),
                confidence=0.95,
                source="pattern",
                description="Class definition"
            )
        
        # Common Python patterns
        if current_line.strip() == 'if':
            return GhostSuggestion(
                text=" condition:",
                trigger_position=len(current_line),
                confidence=0.8,
                source="pattern",
                description="If statement"
            )
        
        if current_line.strip() == 'for':
            return GhostSuggestion(
                text=" item in items:",
                trigger_position=len(current_line),
                confidence=0.8,
                source="pattern",
                description="For loop"
            )
        
        # Import patterns
        if current_line.strip().startswith('from ') and ' import' not in current_line:
            return GhostSuggestion(
                text=" import ",
                trigger_position=len(current_line),
                confidence=0.85,
                source="pattern",
                description="Import statement"
            )
        
        # Return type hints (Python)
        if 'def ' in context and '->' not in current_line and current_line.strip().endswith(')'):
            return GhostSuggestion(
                text=" -> ",
                trigger_position=len(current_line),
                confidence=0.6,
                source="pattern",
                description="Return type hint"
            )
        
        return None
    
    def _get_node_at_position(self, root_node, position: int):
        """Get the AST node at a specific position."""
        for child in root_node.children:
            if child.start_byte <= position <= child.end_byte:
                deeper = self._get_node_at_position(child, position)
                return deeper if deeper else child
        return None
    
    def _generate_contextual_suggestion(
        self,
        node,
        edit_description: str
    ) -> GhostSuggestion | None:
        """Generate suggestion based on AST node context."""
        node_type = node.type
        
        if node_type == "function_definition":
            if "docstring" in edit_description.lower() or "document" in edit_description.lower():
                func_name = "function"
                for child in node.children:
                    if child.type == "identifier":
                        func_name = child.text.decode('utf8')
                        break
                
                return GhostSuggestion(
                    text=f'\n    """\n    {func_name} description.\n    """',
                    trigger_position=node.end_byte,
                    confidence=0.75,
                    source="edit_prediction",
                    description="Add docstring"
                )
        
        return None


# Singleton
ghost_suggester = GhostTextSuggester()


async def suggest_ghost_text(
    file_path: str,
    cursor_line: int,
    cursor_column: int,
    current_line_text: str
) -> GhostSuggestion | None:
    """Tool-friendly wrapper for Ghost Text suggestions."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        position = sum(len(line) for line in lines[:cursor_line-1]) + cursor_column
        
        suggestion = await ghost_suggester.suggest_completion(
            file_path=file_path,
            cursor_position=position,
            current_line=current_line_text
        )
        
        if suggestion:
            return suggestion
        
        return None
        
    except Exception as e:
        logger.error(f"Ghost text suggestion failed: {e}")
        return None
