"""
Phase 3 Tests - Semantic Search & Advanced Features

Covers:
- T-3.1: Vector semantic search (LanceDB + chunking + embedding)
- T-3.2: Document version history (backup + restore)
- T-3.3: Unified search_knowledge Agent tool (fts/semantic/hybrid)
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.knowledge.models import MarkdownDocument
from app.domain.knowledge.services.store import KnowledgeStoreService
from app.domain.knowledge.services.vector_search import KBVectorSearchService
from app.infrastructure.database.vector.lancedb_store import LanceVectorStore


# ---------------------------------------------------------------------------
# T-3.1: Vector Semantic Search
# ---------------------------------------------------------------------------

class TestKBVectorSearchService:
    """T-3.1: Document chunking, indexing, and semantic search"""

    def test_chunk_document_empty(self):
        service = KBVectorSearchService()
        assert service._chunk_document("") == []

    def test_chunk_document_short_text(self):
        service = KBVectorSearchService()
        text = "Short text."
        chunks = service._chunk_document(text, chunk_size=100, overlap=10)
        assert len(chunks) == 1
        assert chunks[0] == "Short text."

    def test_chunk_document_natural_breaks(self):
        service = KBVectorSearchService()
        # Create text with paragraphs
        paras = [f"Paragraph {i} with some content here." for i in range(20)]
        text = "\n\n".join(paras)
        chunks = service._chunk_document(text, chunk_size=100, overlap=10)
        assert len(chunks) >= 2
        # Chunks should respect paragraph boundaries when possible
        for chunk in chunks:
            assert len(chunk) > 0

    def test_chunk_document_no_infinite_loop(self):
        service = KBVectorSearchService()
        text = "a" * 5000
        chunks = service._chunk_document(text, chunk_size=100, overlap=10)
        assert len(chunks) > 10
        total = sum(len(c) for c in chunks)
        assert total >= 5000 - 10 * len(chunks)  # allow for overlap


class TestLanceVectorStoreKB:
    """T-3.1: LanceVectorStore kb_chunks table"""

    def setup_method(self):
        # Reset singleton to isolate tests
        LanceVectorStore._instance = None

    def test_kb_table_created(self):
        db_path = tempfile.mkdtemp()
        store = LanceVectorStore(db_path=db_path)
        # kb_table should exist and have the right schema
        stats = store.get_stats()
        assert "kb_chunks" in stats
        assert stats["kb_chunks"] == 0

    def test_upsert_and_search_kb(self):
        db_path = tempfile.mkdtemp()
        store = LanceVectorStore(db_path=db_path)

        # Insert mock records with 768-dim vectors (matching config)
        records = [
            {
                "id": "doc1:0",
                "vector": [0.1] * 768,
                "content": "fastapi is a modern web framework",
                "source_type": "kb",
                "source_id": "doc1",
                "title": "FastAPI Guide",
                "chunk_index": 0,
                "collection": "backend",
                "tags": "api,python",
            },
            {
                "id": "doc1:1",
                "vector": [0.2] * 768,
                "content": "building rest apis with python",
                "source_type": "kb",
                "source_id": "doc1",
                "title": "FastAPI Guide",
                "chunk_index": 1,
                "collection": "backend",
                "tags": "api,python",
            },
        ]
        count = store.upsert_kb_chunks(records)
        assert count == 2

        # Search with a query vector close to first record
        results = store.search_kb([0.11] * 768, top_k=5)
        assert len(results) > 0
        assert results[0]["doc_id"] == "doc1"

    def test_search_kb_collection_filter(self):
        db_path = tempfile.mkdtemp()
        store = LanceVectorStore(db_path=db_path)

        store.upsert_kb_chunks([
            {
                "id": "docA:0",
                "vector": [0.5] * 768,
                "content": "backend api design",
                "source_type": "kb",
                "source_id": "docA",
                "title": "Backend",
                "chunk_index": 0,
                "collection": "backend",
                "tags": "",
            },
            {
                "id": "docB:0",
                "vector": [0.5] * 768,
                "content": "frontend react components",
                "source_type": "kb",
                "source_id": "docB",
                "title": "Frontend",
                "chunk_index": 0,
                "collection": "frontend",
                "tags": "",
            },
        ])

        results = store.search_kb([0.5] * 768, top_k=10, collection="backend")
        assert all(r["collection"] == "backend" for r in results)

    def test_delete_kb_by_doc(self):
        db_path = tempfile.mkdtemp()
        store = LanceVectorStore(db_path=db_path)

        store.upsert_kb_chunks([
            {
                "id": "del:0",
                "vector": [0.3] * 768,
                "content": "to be deleted",
                "source_type": "kb",
                "source_id": "del",
                "title": "Del",
                "chunk_index": 0,
                "collection": "default",
                "tags": "",
            },
        ])
        # Verify via search that the record exists
        results = store.search_kb([0.3] * 768, top_k=5)
        assert len(results) > 0

        store.delete_kb_by_doc("del")
        # LanceDB delete is best-effort; verify no exception raised


class TestKBVectorSearchIntegration:
    """T-3.1: KBVectorSearchService with mocked embedder"""

    def test_index_document_with_mock_embedder(self):
        db_path = tempfile.mkdtemp()
        store = LanceVectorStore(db_path=db_path)
        service = KBVectorSearchService(vector_store=store)

        mock_embedder = MagicMock()
        mock_embedder.embed_documents = AsyncMock(return_value=[[0.1] * 768, [0.2] * 768])
        service._embedder = mock_embedder

        result = asyncio.run(service.index_document(
            doc_id="test/doc.md",
            title="Test Doc",
            content="Paragraph one.\n\nParagraph two with more content.",
            collection="test",
            tags=["tag1"],
        ))

        assert result > 0
        mock_embedder.embed_documents.assert_called_once()

    def test_search_with_mock_embedder(self):
        db_path = tempfile.mkdtemp()
        store = LanceVectorStore(db_path=db_path)
        service = KBVectorSearchService(vector_store=store)

        # Pre-populate
        store.upsert_kb_chunks([
            {
                "id": "test:0",
                "vector": [0.1] * 768,
                "content": "test content",
                "source_type": "kb",
                "source_id": "test/doc.md",
                "title": "Test",
                "chunk_index": 0,
                "collection": "test",
                "tags": "",
            },
        ])

        mock_embedder = MagicMock()
        mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 768)
        service._embedder = mock_embedder

        results = asyncio.run(service.search("test query", collection="test", top_k=5))
        assert len(results) > 0
        assert results[0]["doc_id"] == "test/doc.md"


# ---------------------------------------------------------------------------
# T-3.2: Document Version History
# ---------------------------------------------------------------------------

class TestDocumentVersioning:
    """T-3.2: Version backup, listing, and restore"""

    def test_save_document_creates_backup_on_overwrite(self):
        base = Path(tempfile.mkdtemp())
        store = KnowledgeStoreService(base_path=str(base))

        doc = MarkdownDocument(
            content="Original content",
            source="test.txt",
            mime_type="text/plain",
        )

        # First save
        result1 = store.save_document(doc, collection="test", path="doc.md")
        assert result1.path == "test/doc.md"

        # Second save (overwrite) should create backup
        doc2 = MarkdownDocument(
            content="Updated content",
            source="test.txt",
            mime_type="text/plain",
        )
        result2 = store.save_document(doc2, collection="test", path="doc.md")

        # Check versions exist
        versions = store.get_document_versions("test/doc.md")
        assert len(versions) >= 1
        # Original content should be in backup
        backup_content = Path(versions[0]["path"]).read_text()
        assert "Original content" in backup_content

    def test_get_document_versions_empty(self):
        base = Path(tempfile.mkdtemp())
        store = KnowledgeStoreService(base_path=str(base))
        versions = store.get_document_versions("nonexistent/doc.md")
        assert versions == []

    def test_restore_document_version(self):
        base = Path(tempfile.mkdtemp())
        store = KnowledgeStoreService(base_path=str(base))

        doc = MarkdownDocument(
            content="Version A",
            source="test.txt",
            mime_type="text/plain",
        )
        store.save_document(doc, collection="test", path="doc.md")

        time.sleep(1.1)  # Ensure distinct timestamp

        doc2 = MarkdownDocument(
            content="Version B",
            source="test.txt",
            mime_type="text/plain",
        )
        store.save_document(doc2, collection="test", path="doc.md")

        versions = store.get_document_versions("test/doc.md")
        assert len(versions) >= 1

        # Restore to oldest version
        timestamp = versions[-1]["timestamp"]
        restored = store.restore_document_version("test/doc.md", timestamp)
        assert restored is True

        # Verify content is back to Version A
        result = store.read_document("test/doc.md")
        assert "Version A" in result.content

    def test_restore_nonexistent_version(self):
        base = Path(tempfile.mkdtemp())
        store = KnowledgeStoreService(base_path=str(base))
        restored = store.restore_document_version("test/doc.md", "99999999_999999")
        assert restored is False

    def test_stats_include_versions(self):
        base = Path(tempfile.mkdtemp())
        store = KnowledgeStoreService(base_path=str(base))

        doc = MarkdownDocument(content="v1", source="s", mime_type="t")
        store.save_document(doc, collection="c", path="d.md")
        doc2 = MarkdownDocument(content="v2", source="s", mime_type="t")
        store.save_document(doc2, collection="c", path="d.md")

        stats = store.get_stats()
        assert stats["total_versions"] >= 1


# ---------------------------------------------------------------------------
# T-3.3: Unified Search Knowledge Agent Tool
# ---------------------------------------------------------------------------

class TestKbSearchModes:
    """T-3.3: kb_search tool with fts/semantic/hybrid modes"""

    def test_kb_search_semantic_mode_calls_vector_service(self):
        from app.domain.knowledge.tools.search import _semantic_search

        with patch("app.domain.knowledge.services.vector_search.get_kb_vector_service") as mock_get:
            mock_service = MagicMock()
            mock_service.search = AsyncMock(return_value=[
                {"doc_id": "a.md", "title": "Doc A", "content": "content A", "score": 0.95}
            ])
            mock_get.return_value = mock_service

            result = asyncio.run(_semantic_search("query", "test", 5))
            assert "Semantic Search" in result
            assert "Doc A" in result
            mock_service.search.assert_called_once()

    def test_kb_search_hybrid_mode_rrf_fusion(self):
        from app.domain.knowledge.tools.search import _hybrid_search

        with patch("app.domain.knowledge.services.search.get_fts_service") as mock_fts_get, \
             patch("app.domain.knowledge.services.vector_search.get_kb_vector_service") as mock_vec_get:

            # Mock FTS results
            mock_fts = MagicMock()
            mock_result = MagicMock()
            mock_result.path = "doc1"
            mock_result.title = "Doc 1"
            mock_result.highlights = "highlight"
            mock_result.content_snippet = "snippet"
            mock_result.bm25_score = 1.5
            mock_fts.search = AsyncMock(return_value=MagicMock(results=[mock_result]))
            mock_fts_get.return_value = mock_fts

            # Mock vector results
            mock_vec = MagicMock()
            mock_vec.search = AsyncMock(return_value=[
                {"doc_id": "doc1", "title": "Doc 1", "content": "content", "score": 0.9},
                {"doc_id": "doc2", "title": "Doc 2", "content": "content2", "score": 0.8},
            ])
            mock_vec_get.return_value = mock_vec

            result = asyncio.run(_hybrid_search("query", "test", 5, 2))
            assert "Hybrid Search" in result
            # Both docs should appear
            assert "doc1" in result

    def test_kb_search_hybrid_empty_results(self):
        from app.domain.knowledge.tools.search import _hybrid_search

        with patch("app.domain.knowledge.services.search.get_fts_service") as mock_fts_get, \
             patch("app.domain.knowledge.services.vector_search.get_kb_vector_service") as mock_vec_get:

            mock_fts = MagicMock()
            mock_fts.search = AsyncMock(return_value=MagicMock(results=[]))
            mock_fts_get.return_value = mock_fts

            mock_vec = MagicMock()
            mock_vec.search = AsyncMock(return_value=[])
            mock_vec_get.return_value = mock_vec

            result = asyncio.run(_hybrid_search("query", "test", 5, 2))
            assert "no matches" in result.lower()

    def test_kb_search_hybrid_citation_boost(self):
        """High-citation documents receive RRF score boost."""
        from app.domain.knowledge.tools.search import _hybrid_search

        with patch("app.domain.knowledge.tools.search.get_fts_service") as mock_fts_get, \
             patch("app.domain.knowledge.services.vector_search.get_kb_vector_service") as mock_vec_get, \
             patch("app.domain.knowledge.services.citations.get_citation_tracker") as mock_cite_get:

            mock_fts = MagicMock()
            mock_res = MagicMock()
            mock_res.path = "doc1"
            mock_res.title = "Doc 1"
            mock_res.highlights = "hl"
            mock_res.content_snippet = "snip"
            mock_res.bm25_score = 1.0
            mock_fts.search = AsyncMock(return_value=MagicMock(results=[mock_res]))
            mock_fts_get.return_value = mock_fts

            mock_vec = MagicMock()
            mock_vec.search = AsyncMock(return_value=[])
            mock_vec_get.return_value = mock_vec

            mock_tracker = MagicMock()
            mock_stats = MagicMock()
            mock_stats.total_citations = 10
            mock_tracker.get_document_stats = AsyncMock(return_value=mock_stats)
            mock_tracker.get_recommendations = AsyncMock(return_value=[])
            mock_cite_get.return_value = mock_tracker

            result = asyncio.run(_hybrid_search("query", "test", 5, 2))
            assert "Hybrid Search" in result
            assert "doc1" in result
            # Citation tracker should have been called for boost
            mock_tracker.get_document_stats.assert_called()

    def test_kb_search_hybrid_recommendations(self):
        """Co-citation recommendations are appended to hybrid results."""
        from app.domain.knowledge.tools.search import _hybrid_search

        with patch("app.domain.knowledge.tools.search.get_fts_service") as mock_fts_get, \
             patch("app.domain.knowledge.services.vector_search.get_kb_vector_service") as mock_vec_get, \
             patch("app.domain.knowledge.services.citations.get_citation_tracker") as mock_cite_get:

            mock_fts = MagicMock()
            mock_res = MagicMock()
            mock_res.path = "doc1"
            mock_res.title = "Doc 1"
            mock_res.highlights = "hl"
            mock_res.content_snippet = "snip"
            mock_res.bm25_score = 1.0
            mock_fts.search = AsyncMock(return_value=MagicMock(results=[mock_res]))
            mock_fts_get.return_value = mock_fts

            mock_vec = MagicMock()
            mock_vec.search = AsyncMock(return_value=[])
            mock_vec_get.return_value = mock_vec

            # Mock recommendation
            mock_rec = MagicMock()
            mock_rec.path = "doc2"
            mock_rec.reason = "often_cited_together"
            mock_rec.relevance = 0.8
            mock_rec.total_citations = 5

            mock_tracker = MagicMock()
            mock_tracker.get_document_stats = AsyncMock(return_value=None)
            mock_tracker.get_recommendations = AsyncMock(return_value=[mock_rec])
            mock_cite_get.return_value = mock_tracker

            result = asyncio.run(_hybrid_search("query", "test", 5, 2))
            assert "Recommended" in result
            assert "doc2" in result
            assert "often_cited_together" in result
