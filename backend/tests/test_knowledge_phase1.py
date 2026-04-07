"""
Phase 1 Tests - Knowledge Base Core Features
"""

import pytest
import asyncio
import tempfile
import os
from io import BytesIO
from pathlib import Path

# Test basic imports
def test_imports():
    """Test that all Phase 1 modules can be imported."""
    from app.domain.knowledge.models import MarkdownDocument, DocumentMetadata
    from app.domain.knowledge.extractors import (
        ExtractorRegistry, PlainTextExtractor, MarkdownExtractor
    )
    from app.domain.knowledge.services.store import KnowledgeStoreService
    from app.domain.knowledge.services.pipeline import IngestionPipeline
    from app.domain.knowledge.tools import kb_read, kb_search, kb_list
    assert True


@pytest.mark.asyncio
async def test_markdown_document():
    """Test MarkdownDocument model."""
    from app.domain.knowledge.models import MarkdownDocument
    
    doc = MarkdownDocument(
        content="# Test\n\nHello World",
        source="test.md",
        mime_type="text/markdown",
        metadata={"title": "Test Doc"}
    )
    
    assert doc.content == "# Test\n\nHello World"
    assert doc.source == "test.md"
    assert doc.metadata["title"] == "Test Doc"
    assert doc.size > 0
    assert doc.line_count == 3
    
    # Test frontmatter
    frontmatter = doc.to_frontmatter()
    assert "---" in frontmatter
    assert "title: Test Doc" in frontmatter


def test_extractors_registry():
    """Test ExtractorRegistry."""
    from app.domain.knowledge.extractors import ExtractorRegistry, PlainTextExtractor
    
    # Clear and register
    ExtractorRegistry.clear()
    ExtractorRegistry.register(PlainTextExtractor())
    
    extractors = ExtractorRegistry.list_extractors()
    assert len(extractors) >= 1
    assert any(e["name"] == "plain_text" for e in extractors)


@pytest.mark.asyncio
async def test_text_extractor():
    """Test PlainTextExtractor."""
    from app.domain.knowledge.extractors import PlainTextExtractor
    
    extractor = PlainTextExtractor()
    
    # Test supports
    assert extractor.supports("text/plain", "test.txt") is True
    assert extractor.supports("application/pdf", "test.pdf") is False
    
    # Test extract
    content = b"Hello, World!\nThis is a test."
    file = BytesIO(content)
    
    doc = await extractor.extract(file, "test.txt")
    assert "Hello, World!" in doc.content
    assert doc.mime_type == "text/plain"


@pytest.mark.asyncio
async def test_markdown_extractor():
    """Test MarkdownExtractor."""
    from app.domain.knowledge.extractors import MarkdownExtractor
    
    extractor = MarkdownExtractor()
    
    # Test with frontmatter
    content = b"---\ntitle: My Doc\n---\n\n# Heading\n\nContent"
    file = BytesIO(content)
    
    doc = await extractor.extract(file, "test.md")
    assert doc.metadata.get("title") == "My Doc"
    assert "# Heading" in doc.content


def test_store_service_init():
    """Test KnowledgeStoreService initialization."""
    from app.domain.knowledge.services.store import KnowledgeStoreService
    
    with tempfile.TemporaryDirectory() as tmpdir:
        store = KnowledgeStoreService(base_path=tmpdir)
        
        # Check directories created
        assert Path(tmpdir).exists()
        assert (Path(tmpdir) / "raw").exists()
        assert (Path(tmpdir) / "meta").exists()


@pytest.mark.asyncio
async def test_store_save_and_read():
    """Test save and read document."""
    from app.domain.knowledge.services.store import KnowledgeStoreService
    from app.domain.knowledge.models import MarkdownDocument
    
    with tempfile.TemporaryDirectory() as tmpdir:
        store = KnowledgeStoreService(base_path=tmpdir)
        
        # Create document
        doc = MarkdownDocument(
            content="# Test Document\n\nThis is a test.",
            source="test.md",
            mime_type="text/markdown",
            metadata={"title": "Test"}
        )
        
        # Save
        result = store.save_document(doc, project="test-project")
        assert "path" in result
        
        # Read
        read_result = store.read_document(result["path"])
        assert read_result["content"] == "# Test Document\n\nThis is a test."


def test_store_list_documents():
    """Test listing documents."""
    from app.domain.knowledge.services.store import KnowledgeStoreService
    from app.domain.knowledge.models import MarkdownDocument
    
    with tempfile.TemporaryDirectory() as tmpdir:
        store = KnowledgeStoreService(base_path=tmpdir)
        
        # Create multiple documents
        for i in range(3):
            doc = MarkdownDocument(
                content=f"Doc {i}",
                source=f"doc{i}.md",
                mime_type="text/markdown"
            )
            store.save_document(doc, project="test")
        
        # List
        docs = store.list_documents("test")
        assert len(docs) == 3


@pytest.mark.asyncio
async def test_kb_list_tool():
    """Test kb_list tool."""
    from app.domain.knowledge.tools.list import kb_list
    
    # Just test it runs without error
    result = await kb_list()
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_kb_search_tool():
    """Test kb_search tool."""
    from app.domain.knowledge.tools.search import kb_search
    
    # Test with no results (empty knowledge base)
    result = await kb_search(pattern="test")
    assert isinstance(result, str)
    assert "No matches" in result or "searched" in result


@pytest.mark.asyncio
async def test_kb_read_tool_not_found():
    """Test kb_read tool with non-existent document."""
    from app.domain.knowledge.tools.read import kb_read
    
    result = await kb_read(path="nonexistent.md")
    assert "not found" in result.lower() or "❌" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
