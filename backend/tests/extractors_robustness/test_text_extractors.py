"""
Robustness tests for Text/Markdown/Code Extractors
"""

import pytest
import io
from app.domain.knowledge.extractors.text import (
    PlainTextExtractor, MarkdownExtractor, CodeDocExtractor
)


class TestPlainTextExtractorRobustness:
    """Test PlainTextExtractor edge cases."""
    
    @pytest.fixture
    def extractor(self):
        return PlainTextExtractor()
    
    @pytest.mark.asyncio
    async def test_empty_file(self, extractor):
        """Handle completely empty files."""
        file = io.BytesIO(b"")
        doc = await extractor.extract(file, "empty.txt")
        assert doc.content == ""
        assert doc.metadata["original_size"] == 0
    
    @pytest.mark.asyncio
    async def test_whitespace_only(self, extractor):
        """Handle files with only whitespace."""
        file = io.BytesIO(b"   \n\t\n   ")
        doc = await extractor.extract(file, "whitespace.txt")
        assert doc.content.strip() == ""
    
    @pytest.mark.asyncio
    async def test_utf8_with_bom(self, extractor):
        """Handle UTF-8 with BOM."""
        content = b"\xef\xbb\xbfHello World"
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "utf8_bom.txt")
        assert "Hello World" in doc.content
    
    @pytest.mark.asyncio
    async def test_utf16_encoding(self, extractor):
        """Handle UTF-16 encoded files."""
        text = "Hello World 中文"
        content = text.encode('utf-16')
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "utf16.txt")
        # Should fallback gracefully
        assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_latin1_encoding(self, extractor):
        """Handle Latin-1 encoded files."""
        text = "Café résumé naïve"
        content = text.encode('latin-1')
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "latin1.txt")
        assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_special_unicode(self, extractor):
        """Handle special unicode characters."""
        special = [
            "日本語テキスト",
            "中文测试内容",
            "한국어 텍스트",
            "العربية",
            "עברית",
            "Ελληνικά",
            "Русский текст",
            "🎉🚀💻🔥",
            "∞≈≠≤≥",
            "€£¥₹",
        ]
        content = "\n\n".join(special).encode('utf-8')
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "unicode.txt")
        assert doc.content is not None
        assert len(doc.content) > 0
    
    @pytest.mark.asyncio
    async def test_binary_garbage(self, extractor):
        """Handle binary garbage input."""
        content = bytes(range(256)) * 10
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "binary.txt")
        assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_very_long_lines(self, extractor):
        """Handle files with very long lines (>10KB)."""
        long_line = "A" * 10000 + "\n"
        file = io.BytesIO(long_line.encode() * 10)
        doc = await extractor.extract(file, "longlines.txt")
        assert "A" * 1000 in doc.content
    
    @pytest.mark.asyncio
    async def test_many_lines(self, extractor):
        """Handle files with many lines (>10000)."""
        lines = "".join(f"Line {i}\n" for i in range(10000))
        file = io.BytesIO(lines.encode())
        doc = await extractor.extract(file, "manylines.txt")
        assert doc.metadata["line_count"] >= 10000
    
    @pytest.mark.asyncio
    async def test_null_bytes(self, extractor):
        """Handle files with null bytes."""
        content = b"Hello\x00World\x00Test"
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "nullbytes.txt")
        assert doc.content is not None
    
    def test_shebang_detection(self, extractor):
        """Test shebang line detection."""
        assert extractor._detect_code("#!/usr/bin/env python3\nprint('hello')", "script") is True
        assert extractor._detect_code("#!/bin/bash\necho hello", "script") is True
        assert extractor._detect_code("#!/usr/bin/node\nconsole.log('hello')", "script") is True
        assert extractor._detect_code("Just plain text", "file.txt") is False


class TestMarkdownExtractorRobustness:
    """Test MarkdownExtractor edge cases."""
    
    @pytest.fixture
    def extractor(self):
        return MarkdownExtractor()
    
    @pytest.mark.asyncio
    async def test_empty_markdown(self, extractor):
        """Handle empty markdown files."""
        file = io.BytesIO(b"")
        doc = await extractor.extract(file, "empty.md")
        assert doc.content == ""
    
    @pytest.mark.asyncio
    async def test_malformed_frontmatter(self, extractor):
        """Handle malformed YAML frontmatter."""
        content = b"---\ninvalid: yaml: : :\n---\n\n# Content"
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "bad_frontmatter.md")
        assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_incomplete_frontmatter(self, extractor):
        """Handle incomplete frontmatter markers."""
        content = b"---\ntitle: Test\n"
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "incomplete.md")
        assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_nested_code_blocks(self, extractor):
        """Handle nested code blocks."""
        content = b"""
# Test

```python
# ```nested
print("hello")
```

```javascript
// ```
console.log("world")
```
"""
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "codeblocks.md")
        assert doc.metadata["code_block_count"] == 3
    
    @pytest.mark.asyncio
    async def test_deeply_nested_headers(self, extractor):
        """Handle deeply nested headers (h1-h6)."""
        content = b"""
# H1
## H2
### H3
#### H4
##### H5
###### H6
####### Not a header
"""
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "headers.md")
        headers = [h for h in doc.metadata.get("headers", []) if h["level"] <= 6]
        assert len(headers) == 6
    
    @pytest.mark.asyncio
    async def test_broken_markdown_syntax(self, extractor):
        """Handle broken markdown syntax gracefully."""
        content = b"""
# Unclosed [link
**unclosed bold
`unclosed code
> unclosed quote
"""
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "broken.md")
        assert doc.content is not None


class TestCodeDocExtractorRobustness:
    """Test CodeDocExtractor edge cases."""
    
    @pytest.fixture
    def extractor(self):
        return CodeDocExtractor()
    
    @pytest.mark.asyncio
    async def test_empty_code_file(self, extractor):
        """Handle empty code files."""
        file = io.BytesIO(b"")
        doc = await extractor.extract(file, "empty.py")
        assert "```python" in doc.content
    
    @pytest.mark.asyncio
    async def test_various_extensions(self, extractor):
        """Test various code file extensions."""
        extensions = [
            ("test.py", "python"),
            ("test.js", "javascript"),
            ("test.ts", "typescript"),
            ("test.jsx", "jsx"),
            ("test.tsx", "tsx"),
            ("test.java", "java"),
            ("test.go", "go"),
            ("test.rs", "rust"),
            ("test.cpp", "cpp"),
            ("test.c", "c"),
            ("test.h", "c"),
        ]
        
        for filename, expected_lang in extensions:
            file = io.BytesIO(b"// test code")
            doc = await extractor.extract(file, filename)
            assert doc.metadata.get("language") == expected_lang, f"Failed for {filename}"
