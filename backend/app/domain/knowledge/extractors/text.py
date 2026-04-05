"""
Basic text extractors for plain text and Markdown files.
"""

from typing import BinaryIO

from app.domain.knowledge.extractors.base import BaseExtractor
from app.domain.knowledge.models import MarkdownDocument


class PlainTextExtractor(BaseExtractor):
    """
    Extractor for plain text files.
    
    Simply reads the text content and wraps it in a MarkdownDocument.
    This is the fallback extractor for unknown text-based formats.
    """
    
    SUPPORTED_EXTENSIONS = {
        '.txt', '.text', '.log', '.csv', '.tsv',
        '.ini', '.conf', '.config', '.env',
        '.sh', '.bash', '.zsh', '.fish',
        '.sql', '.rst'
    }
    
    SUPPORTED_MIME_TYPES = {
        'text/plain',
        'text/csv',
        'text/tab-separated-values',
        'application/x-shellscript',
        'application/sql',
        'text/x-sql'
    }
    
    @property
    def name(self) -> str:
        return "plain_text"
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file is a plain text file."""
        ext = self._get_file_extension(filename)
        
        # Check extension
        if ext in self.SUPPORTED_EXTENSIONS:
            return True
        
        # Check MIME type
        if mime_type in self.SUPPORTED_MIME_TYPES:
            return True
        
        # Check for text/* prefix
        if mime_type.startswith('text/'):
            return True
        
        return False
    
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """Extract plain text content."""
        content = self._read_all(file)
        
        # Try to decode with UTF-8, fallback to latin-1
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')
        
        # Detect if it might be code (has shebang or common patterns)
        is_code = self._detect_code(text, filename)
        
        # Wrap in code block if it looks like code
        if is_code:
            lang = self._detect_language(filename, text)
            formatted_content = f"```{lang}\n{text}\n```"
        else:
            formatted_content = text
        
        return MarkdownDocument(
            content=formatted_content,
            source=filename,
            mime_type="text/plain",
            metadata={
                "original_size": len(content),
                "line_count": text.count('\n') + 1,
                "is_code": is_code,
                "detected_language": self._detect_language(filename, text) if is_code else None
            }
        )
    
    def _detect_code(self, text: str, filename: str) -> bool:
        """Detect if content is code."""
        # Check shebang
        if text.startswith('#!'):
            return True
        
        # Check for common code patterns
        code_indicators = [
            'def ', 'class ', 'import ', 'function ', 'const ', 'var ',
            '#include', 'package ', 'public class', 'func ',
            'if __name__', '<?php', '<!DOCTYPE'
        ]
        first_lines = '\n'.join(text.split('\n')[:20])
        return any(ind in first_lines for ind in code_indicators)
    
    def _detect_language(self, filename: str, text: str) -> str:
        """Detect programming language from filename and content."""
        ext = self._get_file_extension(filename)
        
        lang_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.sh': 'bash',
            '.bash': 'bash',
            '.sql': 'sql',
            '.csv': 'csv',
            '.log': 'text'
        }
        
        if ext in lang_map:
            return lang_map[ext]
        
        # Check shebang
        if text.startswith('#!'):
            first_line = text.split('\n')[0]
            if 'python' in first_line:
                return 'python'
            elif 'bash' in first_line or 'sh' in first_line:
                return 'bash'
        
        return 'text'


class MarkdownExtractor(BaseExtractor):
    """
    Extractor for Markdown files.
    
    Markdown files are already in the target format, so this extractor
    simply reads and validates them. It also extracts metadata from
    YAML frontmatter if present.
    """
    
    @property
    def name(self) -> str:
        return "markdown"
    
    def priority(self) -> int:
        """High priority for markdown files."""
        return 10
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file is Markdown."""
        ext = self._get_file_extension(filename)
        
        if ext in {'.md', '.markdown', '.mdown', '.mkd'}:
            return True
        
        if mime_type in {'text/markdown', 'text/x-markdown'}:
            return True
        
        return False
    
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """
        Extract Markdown content.
        
        If the file has YAML frontmatter, it's parsed and merged into metadata.
        """
        content = self._read_all(file)
        
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')
        
        # Check for frontmatter
        metadata = {}
        content_only = text
        
        if text.startswith('---'):
            try:
                import yaml
                parts = text.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    if isinstance(frontmatter, dict):
                        metadata = frontmatter
                    content_only = parts[2].strip()
            except Exception:
                # If frontmatter parsing fails, treat as regular content
                pass
        
        # Extract structure info
        headers = self._extract_headers(text)
        code_blocks = text.count('```')
        
        return MarkdownDocument(
            content=text,  # Keep full content including frontmatter
            source=filename,
            mime_type="text/markdown",
            metadata={
                **metadata,
                "title": metadata.get('title', headers[0]['title'] if headers else filename),
                "headers": headers,
                "header_count": len(headers),
                "code_block_count": code_blocks // 2,  # Each block has opening and closing
                "word_count": len(text.split()),
            }
        )
    
    def _extract_headers(self, text: str) -> list[dict]:
        """Extract headers from Markdown."""
        import re
        headers = []
        for match in re.finditer(r'^(#{1,6})\s+(.+)$', text, re.MULTILINE):
            level = len(match.group(1))
            title = match.group(2).strip()
            # Calculate approximate line number
            line_num = text[:match.start()].count('\n') + 1
            headers.append({
                'level': level,
                'title': title,
                'line': line_num
            })
        return headers


class CodeDocExtractor(BaseExtractor):
    """
    Extractor for code files - extracts docstrings and comments as documentation.
    
    This is a simplified version. For full AST parsing, use the structured
    extractor in extractors/code/structured.py
    """
    
    CODE_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs',
        '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.swift', '.kt'
    }
    
    @property
    def name(self) -> str:
        return "code_doc"
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file is a code file."""
        ext = self._get_file_extension(filename)
        return ext in self.CODE_EXTENSIONS
    
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """
        Extract documentation from code.
        
        For now, just wraps the code in a markdown code block.
        Full implementation would extract docstrings, comments, etc.
        """
        content = self._read_all(file)
        
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')
        
        ext = self._get_file_extension(filename)
        lang = ext.lstrip('.')
        
        # Map some extensions to language names
        lang_map = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'jsx': 'jsx',
            'tsx': 'tsx',
            'h': 'c',
            'hpp': 'cpp',
            'kt': 'kotlin',
            'rs': 'rust'
        }
        lang = lang_map.get(lang, lang)
        
        # Simple extraction: wrap in code block with file info
        markdown_content = f"""# {filename}

Source code file.

## File Content

```{lang}
{text}
```

## Statistics

- Language: {lang}
- Lines: {text.count(chr(10)) + 1}
- Size: {len(content)} bytes
"""
        
        return MarkdownDocument(
            content=markdown_content,
            source=filename,
            mime_type=f"text/x-{lang}",
            metadata={
                "language": lang,
                "extension": ext,
                "line_count": text.count('\n') + 1,
                "is_source_code": True
            }
        )
