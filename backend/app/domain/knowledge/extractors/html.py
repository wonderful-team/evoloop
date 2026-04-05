"""
HTML extractor using BeautifulSoup for web content.
"""

import logging
from typing import BinaryIO

from app.domain.knowledge.extractors.base import BaseExtractor
from app.domain.knowledge.models import MarkdownDocument, ExtractionError

logger = logging.getLogger(__name__)


class HTMLExtractor(BaseExtractor):
    """
    Extractor for HTML files.
    
    Converts HTML to Markdown, preserving structure:
    - Headers (h1-h6) → Markdown headers
    - Paragraphs → Text blocks
    - Lists → Markdown lists
    - Links → Markdown links
    - Code blocks → Fenced code blocks
    - Tables → Markdown tables
    
    Requires: pip install beautifulsoup4
    """
    
    SUPPORTED_EXTENSIONS = {'.html', '.htm', '.xhtml'}
    SUPPORTED_MIME_TYPES = {
        'text/html',
        'application/xhtml+xml',
        'text/xhtml'
    }
    
    @property
    def name(self) -> str:
        return "html"
    
    def priority(self) -> int:
        """Higher priority than generic text."""
        return 20
    
    async def is_available(self) -> bool:
        """Check if BeautifulSoup is installed."""
        try:
            import bs4
            return True
        except ImportError:
            return False
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file is HTML."""
        ext = self._get_file_extension(filename)
        if ext in self.SUPPORTED_EXTENSIONS:
            return True
        if mime_type in self.SUPPORTED_MIME_TYPES:
            return True
        return False
    
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """Extract HTML content to Markdown."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ExtractionError(
                "BeautifulSoup not installed. Run: pip install beautifulsoup4",
                source=filename
            )
        
        content = self._read_all(file)
        
        # Detect encoding
        encoding = self._detect_encoding(content)
        try:
            html_text = content.decode(encoding)
        except UnicodeDecodeError:
            html_text = content.decode('utf-8', errors='replace')
        
        # Parse HTML
        soup = BeautifulSoup(html_text, 'html.parser')
        
        # Remove script and style elements
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        # Extract title
        title = ""
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
        
        # Convert to Markdown
        markdown_content = self._convert_to_markdown(soup)
        
        # Build final document
        header = f"# {title}\n\n" if title else ""
        final_content = f"{header}{markdown_content}"
        
        return MarkdownDocument(
            content=final_content,
            source=filename,
            mime_type="text/html",
            metadata={
                "title": title,
                "original_encoding": encoding,
                "has_tables": bool(soup.find('table')),
                "has_images": bool(soup.find('img')),
                "has_links": bool(soup.find('a')),
                "heading_count": len(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])),
            }
        )
    
    def _detect_encoding(self, content: bytes) -> str:
        """Detect encoding from meta tag or BOM."""
        # Check for BOM
        if content.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'
        if content.startswith(b'\xff\xfe'):
            return 'utf-16'
        
        # Try to find charset in meta tag
        content_str = content[:1024].decode('utf-8', errors='ignore')
        import re
        
        # Meta charset
        charset_match = re.search(r'<meta[^>]+charset=["\']?([^"\'>\s]+)', content_str, re.IGNORECASE)
        if charset_match:
            return charset_match.group(1)
        
        return 'utf-8'
    
    def _convert_to_markdown(self, soup) -> str:
        """Convert BeautifulSoup object to Markdown."""
        lines = []
        
        # Process body or entire document
        body = soup.find('body') or soup
        
        for element in body.children:
            if hasattr(element, 'name'):
                md = self._element_to_markdown(element)
                if md:
                    lines.append(md)
        
        return '\n\n'.join(lines)
    
    def _element_to_markdown(self, element) -> str:
        """Convert a single HTML element to Markdown."""
        name = element.name
        
        if name is None:
            # Text node
            text = str(element)
            return text.strip() if text.strip() else ""
        
        # Headings
        if name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(name[1])
            text = element.get_text(strip=True)
            return f"{'#' * level} {text}"
        
        # Paragraph
        if name == 'p':
            text = element.get_text(strip=True)
            return text if text else ""
        
        # Lists
        if name == 'ul':
            items = []
            for li in element.find_all('li', recursive=False):
                text = li.get_text(strip=True)
                items.append(f"- {text}")
            return '\n'.join(items)
        
        if name == 'ol':
            items = []
            for i, li in enumerate(element.find_all('li', recursive=False), 1):
                text = li.get_text(strip=True)
                items.append(f"{i}. {text}")
            return '\n'.join(items)
        
        # Code
        if name in ('pre', 'code'):
            # Check for language class
            code_elem = element.find('code') if name == 'pre' else element
            lang = ""
            if code_elem and code_elem.get('class'):
                for cls in code_elem.get('class'):
                    if cls.startswith('language-') or cls.startswith('lang-'):
                        lang = cls.split('-', 1)[1]
                        break
            
            text = element.get_text(strip=True)
            return f"```{lang}\n{text}\n```"
        
        # Blockquote
        if name == 'blockquote':
            text = element.get_text(strip=True)
            return '> ' + '\n> '.join(text.split('\n'))
        
        # Links
        if name == 'a':
            href = element.get('href', '')
            text = element.get_text(strip=True)
            return f"[{text}]({href})"
        
        # Images
        if name == 'img':
            src = element.get('src', '')
            alt = element.get('alt', '')
            return f"![{alt}]({src})"
        
        # Tables (simplified)
        if name == 'table':
            return self._table_to_markdown(element)
        
        # Divs and sections - process children
        if name in ('div', 'section', 'article', 'main'):
            texts = []
            for child in element.children:
                if hasattr(child, 'name'):
                    md = self._element_to_markdown(child)
                    if md:
                        texts.append(md)
            return '\n\n'.join(texts)
        
        # Inline elements within text
        text = element.get_text(strip=True)
        
        # Formatting
        if name in ('strong', 'b'):
            return f"**{text}**"
        if name in ('em', 'i'):
            return f"*{text}*"
        if name == 'code':
            return f"`{text}`"
        if name == 'br':
            return '\n'
        
        return text if text else ""
    
    def _table_to_markdown(self, table) -> str:
        """Convert HTML table to Markdown."""
        rows = []
        
        # Headers
        headers = []
        thead = table.find('thead')
        if thead:
            for th in thead.find_all(['th', 'td']):
                headers.append(th.get_text(strip=True))
        else:
            # Use first row as header
            first_row = table.find('tr')
            if first_row:
                for th in first_row.find_all(['th', 'td']):
                    headers.append(th.get_text(strip=True))
        
        if headers:
            rows.append('| ' + ' | '.join(headers) + ' |')
            rows.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')
        
        # Body rows
        tbody = table.find('tbody') or table
        for tr in tbody.find_all('tr'):
            # Skip first row if used as header
            if not headers and tr == tbody.find('tr'):
                continue
            
            cells = []
            for td in tr.find_all(['td', 'th']):
                cells.append(td.get_text(strip=True))
            
            if cells:
                rows.append('| ' + ' | '.join(cells) + ' |')
        
        return '\n'.join(rows)
