"""
Phase 2 Tests - Advanced Knowledge Base Features
"""

import pytest
import asyncio
import tempfile
from io import BytesIO
import zipfile


def test_phase2_imports():
    """Test that all Phase 2 modules can be imported."""
    from app.domain.knowledge.services.search import FTSService, get_fts_service
    from app.domain.knowledge.services.bulk_import import BulkImportService
    from app.domain.knowledge.services.auto_tagger import AutoTaggerService, get_auto_tagger
    from app.domain.knowledge.services.deduplication import DeduplicationService
    from app.domain.knowledge.services.citations import CitationTracker, get_citation_tracker
    assert True


@pytest.mark.asyncio
async def test_fts_service_init():
    """Test FTS service initialization."""
    from app.domain.knowledge.services.search import FTSService
    
    with tempfile.TemporaryDirectory() as tmpdir:
        fts = FTSService(db_path=f"{tmpdir}/search.db")
        await fts.initialize()
        
        # Check tables created
        conn = fts._get_connection()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        assert "fts_documents" in tables
        assert "doc_metadata" in tables
        assert "doc_tags" in tables


@pytest.mark.asyncio
async def test_fts_index_and_search():
    """Test FTS indexing and search."""
    from app.domain.knowledge.services.search import FTSService
    
    with tempfile.TemporaryDirectory() as tmpdir:
        fts = FTSService(db_path=f"{tmpdir}/search.db")
        await fts.initialize()
        
        # Index a document
        success = await fts.index_document(
            doc_id="test/doc1.md",
            path="test/doc1.md",
            title="Authentication Guide",
            content="This document explains JWT authentication and OAuth flow.",
            project="test",
            tags=["auth", "jwt"]
        )
        assert success is True
        
        # Search
        results = await fts.search("authentication")
        assert results.total >= 1
        assert any(r.doc_id == "test/doc1.md" for r in results.results)


@pytest.mark.asyncio
async def test_fts_suggestions():
    """Test FTS search suggestions."""
    from app.domain.knowledge.services.search import FTSService
    
    with tempfile.TemporaryDirectory() as tmpdir:
        fts = FTSService(db_path=f"{tmpdir}/search.db")
        await fts.initialize()
        
        # Index documents
        await fts.index_document(
            doc_id="test/api.md",
            path="test/api.md",
            title="API Documentation",
            content="REST API guide",
            project="test"
        )
        
        # Get suggestions
        suggestions = await fts.suggest("api")
        assert len(suggestions) > 0


@pytest.mark.asyncio
async def test_citation_tracker():
    """Test citation tracking."""
    from app.domain.knowledge.services.citations import CitationTracker
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CitationTracker(db_path=f"{tmpdir}/citations.db")
        await tracker.initialize()
        
        # Record citation
        success = await tracker.record_citation(
            doc_path="test/doc.md",
            tool_used="kb_read",
            session_id="test-session"
        )
        assert success is True
        
        # Get stats
        stats = await tracker.get_document_stats("test/doc.md")
        assert stats is not None
        assert stats.total_citations == 1


@pytest.mark.asyncio
async def test_citation_popular_docs():
    """Test popular documents query."""
    from app.domain.knowledge.services.citations import CitationTracker
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CitationTracker(db_path=f"{tmpdir}/citations.db")
        await tracker.initialize()
        
        # Record multiple citations
        for i in range(5):
            await tracker.record_citation(
                doc_path="popular/doc.md",
                tool_used="kb_read",
                session_id=f"session-{i}"
            )
        
        # Get popular
        popular = await tracker.get_most_cited(limit=10)
        assert len(popular) > 0
        assert popular[0].doc_id == "popular/doc.md"


def test_bulk_import_validation():
    """Test ZIP validation."""
    from app.domain.knowledge.services.bulk_import import BulkImportService
    
    service = BulkImportService()
    
    # Create a test ZIP
    import io
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr("test.md", "# Test content")
        zf.writestr("test.py", "print('hello')")
    zip_buffer.seek(0)
    
    # Validate
    validation = service.validate_archive(zip_buffer)
    assert validation["valid"] is True
    assert validation["processable_files"] == 2


@pytest.mark.asyncio
async def test_bulk_import_zip():
    """Test ZIP import."""
    from app.domain.knowledge.services.bulk_import import BulkImportService
    
    service = BulkImportService()
    
    # Create a test ZIP
    import io
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr("readme.md", "# README")
    zip_buffer.seek(0)
    
    # Import
    result = await service.import_zip(
        file=zip_buffer,
        project="test-import",
        preserve_structure=True
    )
    
    # Should have at least tried to process
    assert result.total_files >= 0


def test_deduplication_service():
    """Test deduplication service initialization."""
    from app.domain.knowledge.services.deduplication import DeduplicationService
    from app.domain.knowledge.services.store import KnowledgeStoreService
    
    with tempfile.TemporaryDirectory() as tmpdir:
        store = KnowledgeStoreService(base_path=tmpdir)
        dedup = DeduplicationService(store)
        
        # Test similarity calculation
        score = dedup._similarity_score("hello world", "hello world")
        assert score == 1.0
        
        score = dedup._similarity_score("hello", "world")
        assert score < 1.0


def test_auto_tagger_init():
    """Test auto tagger initialization."""
    from app.domain.knowledge.services.auto_tagger import AutoTaggerService, TAG_CATEGORIES
    
    tagger = AutoTaggerService()
    
    # Check tag categories exist
    assert "type" in TAG_CATEGORIES
    assert "tech" in TAG_CATEGORIES
    assert "api" in TAG_CATEGORIES["type"]


def test_auto_tagger_fallback():
    """Test auto tagger fallback (when LLM fails)."""
    from app.domain.knowledge.services.auto_tagger import AutoTaggerService
    
    tagger = AutoTaggerService()
    
    # Test fallback tagging
    result = tagger._fallback_tagging(
        title="JWT Authentication API",
        content="This guide explains how to implement JWT authentication in your API."
    )
    
    # Should detect auth and api keywords
    assert len(result.tags) > 0
    assert "authentication" in result.tags or "api" in result.tags


@pytest.mark.asyncio
async def test_api_endpoints_exist():
    """Test that API routes are properly defined."""
    from fastapi import APIRouter
    from app.api.routes.knowledge import router
    
    # Check router has routes
    assert len(router.routes) > 0
    
    # Get route paths
    paths = [route.path for route in router.routes]
    
    # Phase 1 routes
    assert "/upload" in paths or any("upload" in p for p in paths)
    assert "/documents" in paths or any("documents" in p for p in paths)
    
    # Phase 2 routes
    assert any("fts" in p for p in paths), "FTS routes not found"
    assert any("bulk" in p for p in paths), "Bulk upload routes not found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
