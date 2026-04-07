"""
Robustness tests for HTML Extractor
"""

import pytest
import io
from app.domain.knowledge.extractors.html import HTMLExtractor


class TestHTMLExtractorRobustness:
    """Test HTMLExtractor edge cases."""
    
    @pytest.fixture
    def extractor(self):
        return HTMLExtractor()
    
    @pytest.mark.asyncio
    async def test_empty_html(self, extractor):
        """Handle empty HTML files."""
        file = io.BytesIO(b"")
        doc = await extractor.extract(file, "empty.html")
        assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_malformed_html(self, extractor):
        """Handle malformed HTML."""
        content = b"<html><body><p>Unclosed paragraph<div>Nested</body></html>"
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "malformed.html")
        assert "Unclosed" in doc.content or "Nested" in doc.content
    
    @pytest.mark.asyncio
    async def test_html_entities(self, extractor):
        """Handle HTML entities."""
        content = b"<html><body>&lt;tag&gt; &amp; &quot;quotes&quot;</body></html>"
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "entities.html")
        assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_script_style_removal(self, extractor):
        """Remove script and style tags."""
        content = b"""
<html>
<head><style>body{color:red}</style></head>
<body>
<script>alert('xss')</script>
<p>Real content</p>
</body>
</html>
"""
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "script.html")
        assert "Real content" in doc.content
        assert "alert" not in doc.content
        assert "color:red" not in doc.content
    
    @pytest.mark.asyncio
    async def test_nested_tables(self, extractor):
        """Handle nested tables."""
        content = b"""
<html>
<body>
<table>
  <tr><td>
    <table>
      <tr><td>Nested</td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>
"""
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "tables.html")
        assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_unicode_html(self, extractor):
        """Handle HTML with unicode."""
        content = '<html><body><h1>日本語</h1><p>中文内容</p></body></html>'.encode('utf-8')
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "unicode.html")
        assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_deeply_nested_html(self, extractor):
        """Handle deeply nested HTML structures."""
        depth = 100
        content = "<div>" * depth + "Content" + "</div>" * depth
        file = io.BytesIO(content.encode())
        doc = await extractor.extract(file, "deep.html")
        assert "Content" in doc.content
    
    @pytest.mark.asyncio
    async def test_large_html_file(self, extractor):
        """Handle large HTML files."""
        # Generate 1MB HTML
        paragraphs = "<p>Paragraph with some content</p>\n" * 10000
        content = f"<html><body>{paragraphs}</body></html>"
        file = io.BytesIO(content.encode())
        doc = await extractor.extract(file, "large.html")
        assert doc.content is not None
        assert len(doc.content) > 0
    
    @pytest.mark.asyncio
    async def test_xss_payloads(self, extractor):
        """Handle XSS payloads gracefully."""
        payloads = [
            b"<script>alert('xss')</script>",
            b"<img src=x onerror=alert('xss')>",
            b"<body onload=alert('xss')>",
            b"<iframe src='javascript:alert(1)'>",
            b"<svg onload=alert(1)>",
        ]
        
        for payload in payloads:
            content = b"<html><body>" + payload + b"<p>Safe</p></body></html>"
            file = io.BytesIO(content)
            doc = await extractor.extract(file, "xss.html")
            assert "Safe" in doc.content
            assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_encoding_detection(self, extractor):
        """Test character encoding detection."""
        # UTF-8 BOM
        content = b"\xef\xbb\xbf<html><body>UTF-8 BOM</body></html>"
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "utf8bom.html")
        assert doc.content is not None
        
        # Meta charset
        content = b'<html><head><meta charset="utf-8"></head><body>Test</body></html>'
        file = io.BytesIO(content)
        doc = await extractor.extract(file, "metacharset.html")
        assert doc.content is not None
