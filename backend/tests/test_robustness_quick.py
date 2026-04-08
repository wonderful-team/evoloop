#!/usr/bin/env python3
"""
Quick robustness test for extractors - No external dependencies required
"""

import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def test_text_extractors():
    """Quick test for text extractors robustness"""
    print("\n1. Testing Text Extractors Robustness...")
    
    from app.domain.knowledge.extractors.text import (
        PlainTextExtractor, MarkdownExtractor, CodeDocExtractor
    )
    
    results = []
    
    # Test 1: Empty file
    try:
        extractor = PlainTextExtractor()
        doc = await extractor.extract(io.BytesIO(b""), "empty.txt")
        assert doc.content == ""
        results.append(("Empty file", "✅ PASS"))
    except Exception as e:
        results.append(("Empty file", f"❌ FAIL: {e}"))
    
    # Test 2: Special unicode
    try:
        content = "日本語 中文 한국어 🎉".encode('utf-8')
        doc = await extractor.extract(io.BytesIO(content), "unicode.txt")
        assert doc.content is not None
        results.append(("Special unicode", "✅ PASS"))
    except Exception as e:
        results.append(("Special unicode", f"❌ FAIL: {e}"))
    
    # Test 3: Binary garbage
    try:
        content = bytes(range(256)) * 10
        doc = await extractor.extract(io.BytesIO(content), "binary.txt")
        assert doc.content is not None
        results.append(("Binary garbage", "✅ PASS"))
    except Exception as e:
        results.append(("Binary garbage", f"❌ FAIL: {e}"))
    
    # Test 4: Markdown with frontmatter
    try:
        extractor = MarkdownExtractor()
        content = b"---\ntitle: Test\n---\n\n# Heading"
        doc = await extractor.extract(io.BytesIO(content), "test.md")
        assert doc.metadata.get("title") == "Test"
        results.append(("Markdown frontmatter", "✅ PASS"))
    except Exception as e:
        results.append(("Markdown frontmatter", f"❌ FAIL: {e}"))
    
    # Test 5: Code file
    try:
        extractor = CodeDocExtractor()
        doc = await extractor.extract(io.BytesIO(b"print('hello')"), "test.py")
        assert doc.metadata.get("language") == "python"
        results.append(("Code detection", "✅ PASS"))
    except Exception as e:
        results.append(("Code detection", f"❌ FAIL: {e}"))
    
    for name, status in results:
        print(f"   {status}: {name}")
    
    passed = sum(1 for _, s in results if "PASS" in s)
    print(f"   Total: {passed}/{len(results)} passed")
    return passed == len(results)


async def test_html_extractors():
    """Quick test for HTML extractor robustness"""
    print("\n2. Testing HTML Extractor Robustness...")
    
    try:
        from app.domain.knowledge.extractors.html import HTMLExtractor
    except ImportError:
        print("   ⚠️  Skipped (beautifulsoup4 not installed)")
        return True
    
    results = []
    
    # Test 1: Script removal
    try:
        extractor = HTMLExtractor()
        content = b"<html><body><script>alert('xss')</script><p>Safe</p></body></html>"
        doc = await extractor.extract(io.BytesIO(content), "test.html")
        assert "Safe" in doc.content
        assert "alert" not in doc.content
        results.append(("XSS script removal", "✅ PASS"))
    except Exception as e:
        results.append(("XSS script removal", f"❌ FAIL: {e}"))
    
    # Test 2: Malformed HTML
    try:
        content = b"<html><body><p>Unclosed<div>Nested</body></html>"
        doc = await extractor.extract(io.BytesIO(content), "malformed.html")
        assert doc.content is not None
        results.append(("Malformed HTML", "✅ PASS"))
    except Exception as e:
        results.append(("Malformed HTML", f"❌ FAIL: {e}"))
    
    for name, status in results:
        print(f"   {status}: {name}")
    
    passed = sum(1 for _, s in results if "PASS" in s)
    print(f"   Total: {passed}/{len(results)} passed")
    return passed == len(results)


async def test_registry():
    """Quick test for extractor registry"""
    print("\n3. Testing Extractor Registry Robustness...")
    
    from app.domain.knowledge.extractors import ExtractorRegistry
    from app.domain.knowledge.extractors.text import PlainTextExtractor, MarkdownExtractor
    
    results = []
    
    # Test 1: Priority ordering
    try:
        ExtractorRegistry.clear()
        
        plain = PlainTextExtractor()  # priority 100
        markdown = MarkdownExtractor()  # priority 10
        
        ExtractorRegistry.register(plain)
        ExtractorRegistry.register(markdown)
        
        extractors = ExtractorRegistry._extractors
        assert extractors[0].priority() <= extractors[1].priority()
        results.append(("Priority ordering", "✅ PASS"))
    except Exception as e:
        results.append(("Priority ordering", f"❌ FAIL: {e}"))
    
    # Test 2: No matching extractor
    try:
        extractor = await ExtractorRegistry.get_extractor("unknown/type", "file.xyz")
        assert extractor is None
        results.append(("No matching extractor", "✅ PASS"))
    except Exception as e:
        results.append(("No matching extractor", f"❌ FAIL: {e}"))
    
    # Test 3: All extractors
    try:
        ExtractorRegistry.initialize_defaults()
        extractors = await ExtractorRegistry.list_extractors()
        # Count available extractors
        available = [e for e in extractors if e.get("available", False)]
        count = len(available)
        assert count >= 3  # At least text extractors
        results.append((f"All extractors ({count})", "✅ PASS"))
    except Exception as e:
        results.append(("All extractors", f"❌ FAIL: {e}"))
    
    for name, status in results:
        print(f"   {status}: {name}")
    
    passed = sum(1 for _, s in results if "PASS" in s)
    print(f"   Total: {passed}/{len(results)} passed")
    return passed == len(results)


async def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║     EvoLoop Extractor Robustness - Quick Test              ║
╚════════════════════════════════════════════════════════════╝
""")
    
    results = []
    
    try:
        results.append(("Text Extractors", await test_text_extractors()))
    except Exception as e:
        print(f"   ❌ Text extractors failed: {e}")
        results.append(("Text Extractors", False))
    
    try:
        results.append(("HTML Extractor", await test_html_extractors()))
    except Exception as e:
        print(f"   ❌ HTML extractor failed: {e}")
        results.append(("HTML Extractor", False))
    
    try:
        results.append(("Registry", await test_registry()))
    except Exception as e:
        print(f"   ❌ Registry failed: {e}")
        results.append(("Registry", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("QUICK TEST SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} test suites passed")
    
    if passed == total:
        print("\n🎉 All robustness tests passed!")
    else:
        print("\n⚠️  Some tests failed")
    
    print("\n📁 Full test suite: tests/extractors_robustness/")


if __name__ == "__main__":
    asyncio.run(main())
