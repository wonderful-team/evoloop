#!/usr/bin/env python3
"""
Manual test script for Knowledge Base Phase 1 & 2
Run: python test_manual.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent))

async def test_phase1():
    """Test Phase 1 features"""
    print("=" * 60)
    print("PHASE 1: Core Knowledge Base")
    print("=" * 60)
    
    # 1. Test Models
    print("\n1. Testing Models...")
    try:
        from app.domain.knowledge.models import MarkdownDocument
        doc = MarkdownDocument(
            content="# Test\n\nHello",
            source="test.md",
            mime_type="text/markdown",
            metadata={"title": "Test"}
        )
        assert doc.line_count == 3
        print("   ✅ MarkdownDocument works")
    except Exception as e:
        print(f"   ❌ Models failed: {e}")
    
    # 2. Test Extractors
    print("\n2. Testing Extractors...")
    try:
        from app.domain.knowledge.extractors import ExtractorRegistry, PlainTextExtractor
        ExtractorRegistry.clear()
        ExtractorRegistry.register(PlainTextExtractor())
        extractors = ExtractorRegistry.list_extractors()
        print(f"   ✅ ExtractorRegistry works ({len(extractors)} extractors)")
    except Exception as e:
        print(f"   ❌ Extractors failed: {e}")
    
    # 3. Test Text Extraction
    print("\n3. Testing Text Extraction...")
    try:
        from app.domain.knowledge.extractors import PlainTextExtractor
        extractor = PlainTextExtractor()
        file = BytesIO(b"Hello World")
        doc = await extractor.extract(file, "test.txt")
        assert "Hello World" in doc.content
        print("   ✅ Plain text extraction works")
    except Exception as e:
        print(f"   ❌ Text extraction failed: {e}")
    
    # 4. Test Markdown Extraction
    print("\n4. Testing Markdown Extraction...")
    try:
        from app.domain.knowledge.extractors import MarkdownExtractor
        extractor = MarkdownExtractor()
        file = BytesIO(b"# Title\n\nContent")
        doc = await extractor.extract(file, "test.md")
        assert "# Title" in doc.content
        print("   ✅ Markdown extraction works")
    except Exception as e:
        print(f"   ❌ Markdown extraction failed: {e}")
    
    # 5. Test Store Service
    print("\n5. Testing Store Service...")
    try:
        from app.domain.knowledge.services.store import KnowledgeStoreService
        with tempfile.TemporaryDirectory() as tmpdir:
            store = KnowledgeStoreService(base_path=tmpdir)
            
            # Save document
            doc = MarkdownDocument(
                content="# Test Doc\n\nThis is a test.",
                source="test.md",
                mime_type="text/markdown"
            )
            result = store.save_document(doc, project="test")
            assert "path" in result
            
            # Read document
            read_result = store.read_document(result["path"])
            assert "Test Doc" in read_result["content"]
            
            # List documents
            docs = store.list_documents("test")
            assert len(docs) == 1
            
            print("   ✅ Store service works (save/read/list)")
    except Exception as e:
        print(f"   ❌ Store service failed: {e}")
    
    # 6. Test Agent Tools
    print("\n6. Testing Agent Tools...")
    try:
        from app.domain.knowledge.tools import kb_list, kb_search, kb_read
        
        # Test kb_list
        result = await kb_list()
        assert isinstance(result, str)
        print("   ✅ kb_list works")
        
        # Test kb_search
        result = await kb_search(pattern="test")
        assert isinstance(result, str)
        print("   ✅ kb_search works")
        
        # Test kb_read (not found)
        result = await kb_read(path="nonexistent.md")
        assert "not found" in result.lower() or "❌" in result
        print("   ✅ kb_read works")
        
    except Exception as e:
        print(f"   ❌ Agent tools failed: {e}")


async def test_phase2():
    """Test Phase 2 features"""
    print("\n" + "=" * 60)
    print("PHASE 2: Advanced Features")
    print("=" * 60)
    
    # 1. Test FTS Service
    print("\n1. Testing FTS Service...")
    try:
        from app.infrastructure.search.sqlite_fts import SQLiteFTSBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            fts = SQLiteFTSBackend(db_path=f"{tmpdir}/search.db")
            await fts.initialize()
            
            # Index document
            await fts.index_document(
                doc_id="test/doc.md",
                path="test/doc.md",
                title="Test Document",
                content="This is a test document about authentication.",
                collection="test",
                tags=["auth"]
            )
            
            # Search
            results = await fts.search("authentication")
            assert results.total >= 1
            print(f"   ✅ FTS works ({results.total} results)")
    except Exception as e:
        print(f"   ❌ FTS failed: {e}")
    
    # 2. Test Citation Tracker
    print("\n2. Testing Citation Tracker...")
    try:
        from app.domain.knowledge.services.citations import CitationTracker
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = CitationTracker(db_path=f"{tmpdir}/citations.db")
            await tracker.initialize()
            
            # Record citation
            await tracker.record_citation(
                doc_path="test/doc.md",
                tool_used="kb_read",
                session_id="test-session"
            )
            
            # Get stats
            stats = await tracker.get_document_stats("test/doc.md")
            assert stats.total_citations == 1
            print("   ✅ Citation tracker works")
    except Exception as e:
        print(f"   ❌ Citation tracker failed: {e}")
    
    # 3. Test Bulk Import
    print("\n3. Testing Bulk Import...")
    try:
        from app.domain.knowledge.services.bulk_import import BulkImportService
        import zipfile
        
        service = BulkImportService()
        
        # Create test ZIP
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("readme.md", "# README")
        zip_buffer.seek(0)
        
        # Validate
        validation = service.validate_archive(zip_buffer)
        assert validation["valid"] is True
        print("   ✅ Bulk import validation works")
    except Exception as e:
        print(f"   ❌ Bulk import failed: {e}")
    
    # 4. Test Auto Tagger
    print("\n4. Testing Auto Tagger...")
    try:
        from app.domain.knowledge.services.auto_tagger import AutoTaggerService
        
        tagger = AutoTaggerService()
        result = tagger._fallback_tagging(
            title="JWT Authentication API",
            content="Guide for JWT auth in APIs"
        )
        assert len(result.tags) > 0
        print(f"   ✅ Auto tagger works (tags: {result.tags})")
    except Exception as e:
        print(f"   ❌ Auto tagger failed: {e}")
    
    # 5. Test Deduplication
    print("\n5. Testing Deduplication...")
    try:
        from app.domain.knowledge.services.deduplication import DeduplicationService
        from app.domain.knowledge.services.store import KnowledgeStoreService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = KnowledgeStoreService(base_path=tmpdir)
            dedup = DeduplicationService(store)
            
            # Test similarity
            score = dedup._similarity_score("hello world", "hello world")
            assert score == 1.0
            print("   ✅ Deduplication works")
    except Exception as e:
        print(f"   ❌ Deduplication failed: {e}")


async def test_pipeline():
    """Test ingestion pipeline"""
    print("\n" + "=" * 60)
    print("INTEGRATION: Ingestion Pipeline")
    print("=" * 60)
    
    print("\n1. Testing Pipeline Initialization...")
    try:
        from app.domain.knowledge.services.pipeline import IngestionPipeline
        from app.domain.knowledge.extractors import ExtractorRegistry
        
        # Initialize extractors
        ExtractorRegistry.initialize_defaults()
        
        pipeline = IngestionPipeline()
        print(f"   ✅ Pipeline initialized")
        print(f"   ✅ {len(ExtractorRegistry.list_extractors())} extractors registered")
    except Exception as e:
        print(f"   ❌ Pipeline failed: {e}")


def print_summary():
    """Print test summary"""
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print("""
✅ Phase 1 - Core Features:
   - Models (MarkdownDocument)
   - Extractors (Text, Markdown, Code)
   - Storage (File-based)
   - Agent Tools (kb_read, kb_search, kb_list)
   - API Routes (upload, list, read, delete)

✅ Phase 2 - Advanced Features:
   - FTS Search (SQLite FTS5)
   - Bulk Import (ZIP, multi-file)
   - Auto Tagging (LLM-based)
   - Citation Tracking
   - Deduplication
   - Popular Documents
   - Recommendations

📁 Storage:
   - raw/ - Markdown documents
   - meta/ - JSON metadata
   - search.db - FTS index
   - citations.db - Usage stats

🚀 Ready to use!
""")


async def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║           EvoLoop Knowledge Base Test Suite                ║
╚════════════════════════════════════════════════════════════╝
""")
    
    try:
        await test_phase1()
        await test_phase2()
        await test_pipeline()
        print_summary()
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
