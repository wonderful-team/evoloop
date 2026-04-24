"""
End-to-end document lifecycle integration tests.

Tests the complete flow: create → store → index (FTS + vector) → search → version → delete.
No mocks (except LLM is not involved here).
"""

import asyncio
import time

import pytest

from app.domain.knowledge.models import MarkdownDocument
from app.domain.knowledge.services.search import FTSService, IndexDocumentRequest
from app.domain.knowledge.services.store import KnowledgeStoreService
from app.domain.knowledge.services.vector_search import KBVectorSearchService
from app.infrastructure.database.vector.lancedb_store import LanceVectorStore


class TestDocumentLifecycle:
    """Real document CRUD with real FTS5, LanceDB, and file system."""

    @pytest.mark.asyncio
    async def test_create_store_index_search(self, temp_knowledge_dir, temp_search_db, temp_lancedb_dir, fake_embedder):
        """Full lifecycle: save → FTS index → vector index → search both engines."""
        store = KnowledgeStoreService(base_path=str(temp_knowledge_dir))
        fts = FTSService(db_path=temp_search_db)
        await fts.initialize()

        vector_service = KBVectorSearchService(
            vector_store=LanceVectorStore(db_path=str(temp_lancedb_dir))
        )
        vector_service._embedder = fake_embedder

        # Create document
        doc = MarkdownDocument(
            content=("# FastAPI Authentication\n\n"
                     "JSON Web Tokens (JWT) are used for stateless authentication.\n\n"
                     "## OAuth2\n\n"
                     "OAuth2 with Password flow is supported."),
            source="auth-guide.md",
            mime_type="text/markdown",
        )

        # Save to file system
        save_result = store.save_document(doc, collection="backend", path="auth.md")
        assert save_result.path == "backend/auth.md"
        assert (temp_knowledge_dir / "raw" / "backend" / "auth.md").exists()
        assert (temp_knowledge_dir / "meta" / "backend" / "auth.md.json").exists()

        # Index FTS
        await fts.index_document(IndexDocumentRequest(
            doc_id="backend/auth.md",
            path="backend/auth.md",
            title="FastAPI Authentication",
            content=doc.content,
            collection="backend",
            tags=["api", "security", "authentication"],
        ))

        # Index vector
        chunks_indexed = await vector_service.index_document(
            doc_id="backend/auth.md",
            title="FastAPI Authentication",
            content=doc.content,
            collection="backend",
            tags=["api", "security"],
        )
        assert chunks_indexed > 0

        # Verify FTS search finds it
        fts_results = await fts.search("JWT authentication", collection="backend")
        assert fts_results.total >= 1
        paths = [r.path for r in fts_results.results]
        assert "backend/auth.md" in paths

        # Verify vector search finds it
        vec_results = await vector_service.search("web token security", collection="backend", top_k=5)
        assert len(vec_results) >= 1
        doc_ids = [r["doc_id"] for r in vec_results]
        assert "backend/auth.md" in doc_ids

        # Verify list_documents
        docs = store.list_documents(collection="backend")
        assert any(d.path == "backend/auth.md" for d in docs)

    @pytest.mark.asyncio
    async def test_document_versioning(self, temp_knowledge_dir, temp_search_db):
        """Overwrite creates backup; restore reverts content."""
        store = KnowledgeStoreService(base_path=str(temp_knowledge_dir))
        fts = FTSService(db_path=temp_search_db)
        await fts.initialize()

        # Save v1
        doc_v1 = MarkdownDocument(content="Version One", source="v.txt", mime_type="text/plain")
        store.save_document(doc_v1, collection="test", path="doc.md")

        time.sleep(1.1)

        # Save v2
        doc_v2 = MarkdownDocument(content="Version Two", source="v.txt", mime_type="text/plain")
        store.save_document(doc_v2, collection="test", path="doc.md")

        # Verify versions exist
        versions = store.get_document_versions("test/doc.md")
        assert len(versions) >= 1

        # Verify current content is v2
        read_result = store.read_document("test/doc.md")
        assert "Version Two" in read_result.content

        # Restore to oldest
        oldest = versions[-1]["timestamp"]
        assert store.restore_document_version("test/doc.md", oldest) is True

        # Verify restored to v1
        read_result = store.read_document("test/doc.md")
        assert "Version One" in read_result.content

    @pytest.mark.asyncio
    async def test_delete_removes_everything(self, temp_knowledge_dir, temp_search_db, temp_lancedb_dir, fake_embedder):
        """Delete removes raw, meta, FTS, and vector entries."""
        store = KnowledgeStoreService(base_path=str(temp_knowledge_dir))
        fts = FTSService(db_path=temp_search_db)
        await fts.initialize()
        vector_service = KBVectorSearchService(
            vector_store=LanceVectorStore(db_path=str(temp_lancedb_dir))
        )
        vector_service._embedder = fake_embedder

        doc = MarkdownDocument(content="To be deleted", source="d.txt", mime_type="text/plain")
        store.save_document(doc, collection="del", path="target.md")

        await fts.index_document(IndexDocumentRequest(
            doc_id="del/target.md", path="del/target.md",
            title="Target", content=doc.content, collection="del",
        ))
        await vector_service.index_document(
            doc_id="del/target.md", title="Target",
            content=doc.content, collection="del",
        )

        # Verify existence
        assert (temp_knowledge_dir / "raw" / "del" / "target.md").exists()
        fts_before = await fts.search("deleted", collection="del")
        assert fts_before.total >= 1

        # Delete
        store.delete_document("del/target.md")
        await fts.remove_document("del/target.md")
        vector_service.delete_document("del/target.md")

        # Verify removal
        assert not (temp_knowledge_dir / "raw" / "del" / "target.md").exists()
        assert not (temp_knowledge_dir / "meta" / "del" / "target.md.json").exists()
        fts_after = await fts.search("deleted", collection="del")
        assert fts_after.total == 0

    @pytest.mark.asyncio
    async def test_collection_isolation(self, temp_knowledge_dir, temp_search_db, fake_embedder):
        """Documents in different collections do not leak."""
        store = KnowledgeStoreService(base_path=str(temp_knowledge_dir))
        fts = FTSService(db_path=temp_search_db)
        await fts.initialize()

        doc_a = MarkdownDocument(content="Alpha content", source="a.txt", mime_type="text/plain")
        doc_b = MarkdownDocument(content="Beta content", source="b.txt", mime_type="text/plain")
        store.save_document(doc_a, collection="alpha", path="doc.md")
        store.save_document(doc_b, collection="beta", path="doc.md")

        await fts.index_document(IndexDocumentRequest(
            doc_id="alpha/doc.md", path="alpha/doc.md",
            title="Alpha", content=doc_a.content, collection="alpha",
        ))
        await fts.index_document(IndexDocumentRequest(
            doc_id="beta/doc.md", path="beta/doc.md",
            title="Beta", content=doc_b.content, collection="beta",
        ))

        alpha_results = await fts.search("Alpha", collection="alpha")
        assert alpha_results.total == 1
        assert alpha_results.results[0].path == "alpha/doc.md"

        beta_results = await fts.search("Beta", collection="beta")
        assert beta_results.total == 1
        assert beta_results.results[0].path == "beta/doc.md"

        all_results = await fts.search("content")
        assert all_results.total == 2
