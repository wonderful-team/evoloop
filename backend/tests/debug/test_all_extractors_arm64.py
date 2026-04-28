#!/usr/bin/env python3
"""
Test all extractors on ARM64 architecture - No pytest required
"""

import asyncio
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


class ExtractorTestSuite:
    def __init__(self):
        self.results = []
        
    def add_result(self, category, name, passed, error=None):
        self.results.append({
            "category": category,
            "name": name,
            "passed": passed,
            "error": error
        })
        status = "✅" if passed else "❌"
        msg = f"  {status} {category}/{name}"
        if error:
            msg += f": {error}"
        print(msg)
    
    def summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        print(f"\n{'='*60}")
        print(f"SUMMARY: {passed}/{total} tests passed")
        print(f"{'='*60}")
        return passed == total


async def test_text_extractors():
    """Test text extractors"""
    from app.domain.knowledge.extractors.text import (
        PlainTextExtractor, MarkdownExtractor, CodeDocExtractor
    )
    
    suite = ExtractorTestSuite()
    
    # PlainText tests
    extractor = PlainTextExtractor()
    
    # Empty file
    try:
        doc = await extractor.extract(io.BytesIO(b""), "empty.txt")
        suite.add_result("PlainText", "empty_file", doc.content == "")
    except Exception as e:
        suite.add_result("PlainText", "empty_file", False, str(e))
    
    # Normal text
    try:
        doc = await extractor.extract(io.BytesIO(b"Hello World"), "test.txt")
        suite.add_result("PlainText", "normal_text", doc.content == "Hello World")
    except Exception as e:
        suite.add_result("PlainText", "normal_text", False, str(e))
    
    # Unicode
    try:
        content = "日本語テスト".encode('utf-8')
        doc = await extractor.extract(io.BytesIO(content), "unicode.txt")
        suite.add_result("PlainText", "unicode", "日本語" in doc.content)
    except Exception as e:
        suite.add_result("PlainText", "unicode", False, str(e))
    
    # Markdown tests
    md_extractor = MarkdownExtractor()
    
    # With frontmatter
    try:
        content = b"---\ntitle: Test Doc\nauthor: John\n---\n\n# Heading\n\nContent"
        doc = await md_extractor.extract(io.BytesIO(content), "test.md")
        has_title = doc.metadata.get("title") == "Test Doc"
        has_heading = "# Heading" in doc.content
        suite.add_result("Markdown", "with_frontmatter", has_title and has_heading)
    except Exception as e:
        suite.add_result("Markdown", "with_frontmatter", False, str(e))
    
    # Without frontmatter
    try:
        content = b"# Simple Doc\n\nJust content"
        doc = await md_extractor.extract(io.BytesIO(content), "simple.md")
        suite.add_result("Markdown", "no_frontmatter", "# Simple Doc" in doc.content)
    except Exception as e:
        suite.add_result("Markdown", "no_frontmatter", False, str(e))
    
    # CodeDoc tests
    code_extractor = CodeDocExtractor()
    
    # Python file
    try:
        doc = await code_extractor.extract(io.BytesIO(b"def hello(): pass"), "test.py")
        suite.add_result("CodeDoc", "python_detection", doc.metadata.get("language") == "python")
    except Exception as e:
        suite.add_result("CodeDoc", "python_detection", False, str(e))
    
    # JavaScript file
    try:
        doc = await code_extractor.extract(io.BytesIO(b"function hello() {}"), "test.js")
        suite.add_result("CodeDoc", "javascript_detection", doc.metadata.get("language") == "javascript")
    except Exception as e:
        suite.add_result("CodeDoc", "javascript_detection", False, str(e))
    
    return suite.summary()


async def test_html_extractor():
    """Test HTML extractor"""
    try:
        from app.domain.knowledge.extractors.html import HTMLExtractor
    except ImportError as e:
        print(f"  ⚠️  HTML extractor skipped (dependency missing): {e}")
        return True
    
    suite = ExtractorTestSuite()
    extractor = HTMLExtractor()
    
    # Basic HTML
    try:
        content = b"<html><body><h1>Title</h1><p>Paragraph</p></body></html>"
        doc = await extractor.extract(io.BytesIO(content), "test.html")
        suite.add_result("HTML", "basic", "Title" in doc.content and "Paragraph" in doc.content)
    except Exception as e:
        suite.add_result("HTML", "basic", False, str(e))
    
    # Script removal (XSS protection)
    try:
        content = b"<html><body><script>alert('xss')</script><p>Safe</p></body></html>"
        doc = await extractor.extract(io.BytesIO(content), "xss.html")
        suite.add_result("HTML", "xss_protection", "Safe" in doc.content and "alert" not in doc.content)
    except Exception as e:
        suite.add_result("HTML", "xss_protection", False, str(e))
    
    # Malformed HTML
    try:
        content = b"<html><body><p>Unclosed<div>Nested</body></html>"
        doc = await extractor.extract(io.BytesIO(content), "malformed.html")
        suite.add_result("HTML", "malformed", doc.content is not None)
    except Exception as e:
        suite.add_result("HTML", "malformed", False, str(e))
    
    return suite.summary()


async def test_pdf_extractors():
    """Test PDF extractors"""
    try:
        from app.domain.knowledge.extractors.pdf import PDFExtractor, PyPDF2Extractor
    except ImportError as e:
        print(f"  ⚠️  PDF extractors skipped (dependency missing): {e}")
        return True
    
    suite = ExtractorTestSuite()
    
    # Note: We can't test actual PDF extraction without real PDF files
    # But we can test availability
    
    pdf_extractor = PDFExtractor()
    try:
        available = await pdf_extractor.is_available()
        suite.add_result("PDF", "pdfplumber_available", available)
    except Exception as e:
        suite.add_result("PDF", "pdfplumber_available", False, str(e))
    
    pypdf_extractor = PyPDF2Extractor()
    try:
        available = await pypdf_extractor.is_available()
        suite.add_result("PDF", "pypdf2_available", available)
    except Exception as e:
        suite.add_result("PDF", "pypdf2_available", False, str(e))
    
    # Priority check
    try:
        suite.add_result("PDF", "priority", pdf_extractor.priority() < pypdf_extractor.priority())
    except Exception as e:
        suite.add_result("PDF", "priority", False, str(e))
    
    return suite.summary()


async def test_office_extractors():
    """Test Office extractors"""
    try:
        from app.domain.knowledge.extractors.office import (
            WordExtractor, ExcelExtractor, PowerPointExtractor
        )
    except ImportError as e:
        print(f"  ⚠️  Office extractors skipped (dependency missing): {e}")
        return True
    
    suite = ExtractorTestSuite()
    
    # Word
    word_ext = WordExtractor()
    try:
        available = await word_ext.is_available()
        suite.add_result("Office", "word_available", available)
    except Exception as e:
        suite.add_result("Office", "word_available", False, str(e))
    
    # Excel
    excel_ext = ExcelExtractor()
    try:
        available = await excel_ext.is_available()
        suite.add_result("Office", "excel_available", available)
    except Exception as e:
        suite.add_result("Office", "excel_available", False, str(e))
    
    # PowerPoint
    ppt_ext = PowerPointExtractor()
    try:
        available = await ppt_ext.is_available()
        suite.add_result("Office", "powerpoint_available", available)
    except Exception as e:
        suite.add_result("Office", "powerpoint_available", False, str(e))
    
    return suite.summary()


async def test_registry():
    """Test extractor registry"""
    from app.domain.knowledge.extractors import ExtractorRegistry
    from app.domain.knowledge.extractors.text import PlainTextExtractor, MarkdownExtractor
    
    suite = ExtractorTestSuite()
    
    # Clear and register
    ExtractorRegistry.clear()
    
    # Priority ordering
    try:
        plain = PlainTextExtractor()  # priority 100
        markdown = MarkdownExtractor()  # priority 10
        
        ExtractorRegistry.register(plain)
        ExtractorRegistry.register(markdown)
        
        extractors = ExtractorRegistry._extractors
        suite.add_result("Registry", "priority_order", extractors[0].priority() <= extractors[1].priority())
    except Exception as e:
        suite.add_result("Registry", "priority_order", False, str(e))
    
    # Get extractor
    try:
        extractor = await ExtractorRegistry.get_extractor("text/plain", "file.txt")
        suite.add_result("Registry", "get_extractor", extractor is not None)
    except Exception as e:
        suite.add_result("Registry", "get_extractor", False, str(e))
    
    # No matching extractor
    try:
        extractor = await ExtractorRegistry.get_extractor("unknown/type", "file.xyz")
        suite.add_result("Registry", "no_match", extractor is None)
    except Exception as e:
        suite.add_result("Registry", "no_match", False, str(e))
    
    # Initialize defaults
    try:
        ExtractorRegistry.initialize_defaults()
        extractors = await ExtractorRegistry.list_extractors()
        available = [e for e in extractors if e.get("available", False)]
        suite.add_result("Registry", "defaults_loaded", len(available) >= 3)
    except Exception as e:
        suite.add_result("Registry", "defaults_loaded", False, str(e))
    
    return suite.summary()


async def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║     EvoLoop All Extractors Test - ARM64 Edition            ║
╚════════════════════════════════════════════════════════════╝
""")
    
    results = []
    
    print("\n📄 1. Testing Text Extractors...")
    results.append(("Text", await test_text_extractors()))
    
    print("\n🌐 2. Testing HTML Extractor...")
    results.append(("HTML", await test_html_extractor()))
    
    print("\n📑 3. Testing PDF Extractors...")
    results.append(("PDF", await test_pdf_extractors()))
    
    print("\n📊 4. Testing Office Extractors...")
    results.append(("Office", await test_office_extractors()))
    
    print("\n🗂️  5. Testing Registry...")
    results.append(("Registry", await test_registry()))
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} test suites passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n⚠️ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
