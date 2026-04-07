"""
Tests for document extractors.
"""

import pytest
from io import BytesIO

from app.domain.knowledge.extractors import (
    ExtractorRegistry,
    PlainTextExtractor,
    MarkdownExtractor,
    CodeDocExtractor,
    HTMLExtractor,
)
from app.domain.knowledge.models import MarkdownDocument


class TestPlainTextExtractor:
    """Tests for PlainTextExtractor."""
    
    @pytest.fixture
    def extractor(self):
        return PlainTextExtractor()
    
    @pytest.mark.asyncio
    async def test_extract_simple_text(self, extractor):
        """Test extracting simple text file."""
        content = b"Hello, World!\nThis is a test."
        file = BytesIO(content)
        
        result = await extractor.extract(file, "test.txt")
        
        assert isinstance(result, MarkdownDocument)
        assert "Hello, World!" in result.content
        assert result.mime_type == "text/plain"
        assert result.metadata["original_size"] == len(content)
    
    @pytest.mark.asyncio
    async def test_detect_code_python(self, extractor):
        """Test detecting Python code."""
        content = b"#!/usr/bin/env python3\ndef hello():\n    pass"
        file = BytesIO(content)
        
        result = await extractor.extract(file, "script.py")
        
        assert result.metadata["is_code"] is True
        assert "python" in result.metadata["detected_language"]
    
    def test_supports_txt_extension(self, extractor):
        """Test that .txt files are supported."""
        assert extractor.supports("text/plain", "document.txt") is True
    
    def test_supports_py_extension(self, extractor):
        """Test that .py files are supported."""
        assert extractor.supports("text/x-python", "script.py") is True


class TestMarkdownExtractor:
    """Tests for MarkdownExtractor."""
    
    @pytest.fixture
    def extractor(self):
        return MarkdownExtractor()
    
    @pytest.mark.asyncio
    async def test_extract_markdown(self, extractor):
        """Test extracting markdown file."""
        content = b"# Title\n\nThis is **bold** text."
        file = BytesIO(content)
        
        result = await extractor.extract(file, "test.md")
        
        assert isinstance(result, MarkdownDocument)
        assert "# Title" in result.content
        assert result.mime_type == "text/markdown"
    
    @pytest.mark.asyncio
    async def test_extract_frontmatter(self, extractor):
        """Test extracting YAML frontmatter."""
        content = b"---\ntitle: My Doc\nauthor: Test\n---\n\n# Content"
        file = BytesIO(content)
        
        result = await extractor.extract(file, "test.md")
        
        assert result.metadata.get("title") == "My Doc"
        assert "My Doc" in result.content or "Content" in result.content
    
    def test_supports_md_extension(self, extractor):
        """Test that .md files are supported."""
        assert extractor.supports("text/markdown", "README.md") is True


class TestCodeDocExtractor:
    """Tests for CodeDocExtractor."""
    
    @pytest.fixture
    def extractor(self):
        return CodeDocExtractor()
    
    @pytest.mark.asyncio
    async def test_extract_python_code(self, extractor):
        """Test extracting Python code."""
        content = b"def hello():\n    return 'world'"
        file = BytesIO(content)
        
        result = await extractor.extract(file, "hello.py")
        
        assert isinstance(result, MarkdownDocument)
        assert "```python" in result.content
        assert result.metadata["language"] == "python"
    
    @pytest.mark.asyncio
    async def test_extract_javascript_code(self, extractor):
        """Test extracting JavaScript code."""
        content = b"function hello() { return 'world'; }"
        file = BytesIO(content)
        
        result = await extractor.extract(file, "hello.js")
        
        assert result.metadata["language"] == "javascript"


class TestHTMLExtractor:
    """Tests for HTMLExtractor."""
    
    @pytest.fixture
    def extractor(self):
        return HTMLExtractor()
    
    @pytest.mark.asyncio
    async def test_extract_html(self, extractor):
        """Test extracting HTML to Markdown."""
        content = b"""<html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Heading</h1>
            <p>Paragraph text</p>
        </body>
        </html>"""
        file = BytesIO(content)
        
        result = await extractor.extract(file, "test.html")
        
        assert isinstance(result, MarkdownDocument)
        assert "# Heading" in result.content or "Heading" in result.content
        assert result.metadata["title"] == "Test Page"
    
    def test_supports_html_extension(self, extractor):
        """Test that .html files are supported."""
        assert extractor.supports("text/html", "page.html") is True


class TestExtractorRegistry:
    """Tests for ExtractorRegistry."""
    
    def test_register_extractor(self):
        """Test registering an extractor."""
        registry = ExtractorRegistry
        registry.clear()
        
        extractor = PlainTextExtractor()
        registry.register(extractor)
        
        assert len(registry._extractors) == 1
        assert registry._extractors[0].name == "plain_text"
    
    @pytest.mark.asyncio
    async def test_get_extractor_for_text(self):
        """Test getting extractor for text file."""
        registry = ExtractorRegistry
        registry.clear()
        registry.register(PlainTextExtractor())
        registry.register(MarkdownExtractor())
        
        extractor = await registry.get_extractor("text/plain", "test.txt")
        
        assert extractor is not None
        assert extractor.name == "plain_text"
    
    @pytest.mark.asyncio
    async def test_get_extractor_for_markdown(self):
        """Test getting extractor for markdown file."""
        registry = ExtractorRegistry
        registry.clear()
        registry.register(PlainTextExtractor())
        registry.register(MarkdownExtractor())
        
        extractor = await registry.get_extractor("text/markdown", "README.md")
        
        assert extractor is not None
        # Markdown has higher priority (lower number)
        assert extractor.name == "markdown"
    
    @pytest.mark.asyncio
    async def test_get_extractor_not_found(self):
        """Test getting extractor for unsupported file."""
        registry = ExtractorRegistry
        registry.clear()
        registry.register(PlainTextExtractor())
        
        extractor = await registry.get_extractor("application/unknown", "test.xyz")
        
        assert extractor is None
