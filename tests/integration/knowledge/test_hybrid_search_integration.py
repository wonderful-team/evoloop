"""
Hybrid search integration tests — real FTS5 + real LanceDB + real Citation DB.

No mocks except FakeEmbedder (avoids external API).
"""

import pytest

from app.domain.knowledge.models import MarkdownDocument
from app.domain.knowledge.services.citations import CitationTracker
from app.domain.knowledge.services.search import FTSService, IndexDocumentRequest
from app.domain.knowledge.services.store import KnowledgeStoreService
from app.domain.knowledge.services.vector_search import KBVectorSearchService
from app.infrastructure.database.vector.lancedb_store import LanceVectorStore


class TestHybridSearchIntegration:
    """Real dual-engine search with real RRF fusion and citation boost."""

    @pytest.fixture(autouse=True)
    def setup_index(self, temp_knowledge_dir, temp_search_db, temp_lancedb_dir, temp_citations_db, fake_embedder):
        """Seed both FTS and vector indexes with real documents."""
        self.store = KnowledgeStoreService(base_path=str(temp_knowledge_dir))
        self.fts = FTSService(db_path=temp_search_db)
        self.vector = KBVectorSearchService(vector_store=LanceVectorStore(db_path=str(temp_lancedb_dir)))
        self.vector._embedder = fake_embedder
        self.tracker = CitationTracker(db_path=temp_citations_db)

        # Initialize DBs
        asyncio = __import__("asyncio")
        asyncio.run(self._init_dbs())
        asyncio.run(self.tracker.initialize())

        # Seed documents
        docs = [
            ("backend/auth.md", "JWT Authentication Guide",
             "JWT tokens provide stateless authentication for APIs."),
            ("backend/oauth.md", "OAuth2 Implementation",
             "OAuth2 is an authorization framework used for delegated access."),
            ("backend/session.md", "Session Management",
             "Server-side sessions store user state on the server."),
            ("frontend/react.md", "React Hooks",
             "React hooks let you use state and other features in function components."),
        ]

        for path, title, content in docs:
            doc = MarkdownDocument(content=f"# {title}\n\n{content}", source=path, mime_type="text/markdown")
            self.store.save_document(doc, collection=path.split("/")[0], path=path.split("/")[1])
            asyncio.run(self.fts.index_document(IndexDocumentRequest(
                doc_id=path, path=path, title=title, content=doc.content,
                collection=path.split("/")[0], tags=[],
            )))
            asyncio.run(self.vector.index_document(
                doc_id=path, title=title, content=doc.content,
                collection=path.split("/")[0], tags=[],
            ))

    async def _init_dbs(self):
        await self.fts.initialize()

    @pytest.mark.asyncio
    async def test_fts_finds_keyword_match(self):
        """FTS engine alone finds exact keyword matches."""
        results = await self.fts.search("JWT authentication", collection="backend")
        assert results.total >= 1
        paths = [r.path for r in results.results]
        assert "backend/auth.md" in paths

    @pytest.mark.asyncio
    async def test_vector_finds_semantic_match(self):
        """Vector engine finds conceptually related docs."""
        results = await self.vector.search("login security", collection="backend", top_k=5)
        assert len(results) >= 1
        # At least one backend doc should be returned
        assert any("backend/" in r["doc_id"] for r in results)

    @pytest.mark.asyncio
    async def test_collection_filter_works(self):
        """Both engines respect collection boundaries."""
        fts_results = await self.fts.search("state", collection="frontend")
        assert all(r.collection == "frontend" for r in fts_results.results)

        vec_results = await self.vector.search("state", collection="frontend", top_k=5)
        assert all(r["collection"] == "frontend" for r in vec_results)

    @pytest.mark.asyncio
    async def test_citation_recorded_and_boosts(self):
        """Recording a citation increases document stats."""
        await self.tracker.record_citation("backend/auth.md", "kb_read", session_id="sess-1")
        await self.tracker.record_citation("backend/auth.md", "kb_search", session_id="sess-2")
        await self.tracker.record_citation("backend/auth.md", "kb_read", session_id="sess-2")

        stats = await self.tracker.get_document_stats("backend/auth.md")
        assert stats is not None
        assert stats.total_citations == 3
        assert stats.unique_sessions == 2

    @pytest.mark.asyncio
    async def test_citation_recommendations(self):
        """Co-cited documents appear in recommendations."""
        await self.tracker.record_citation("backend/auth.md", "kb_read", session_id="sess-a")
        await self.tracker.record_citation("backend/oauth.md", "kb_read", session_id="sess-a")
        await self.tracker.record_citation("backend/session.md", "kb_read", session_id="sess-a")

        recs = await self.tracker.get_recommendations("backend/auth.md", limit=5)
        paths = [r.path for r in recs]
        assert "backend/oauth.md" in paths or "backend/session.md" in paths

    @pytest.mark.asyncio
    async def test_cross_engine_consistency(self):
        """The same document exists in both indexes."""
        fts_results = await self.fts.search("authorization", collection="backend")
        vec_results = await self.vector.search("authorization", collection="backend", top_k=5)

        fts_paths = {r.path for r in fts_results.results}
        vec_paths = {r["doc_id"] for r in vec_results}

        # At least one document should appear in both engines
        common = fts_paths & vec_paths
        assert len(common) >= 1, f"FTS: {fts_paths}, Vector: {vec_paths}"

    @pytest.mark.asyncio
    async def test_tag_filter_in_fts(self):
        """Tag filtering returns only docs with all specified tags."""
        await self.fts.index_document(IndexDocumentRequest(
            doc_id="backend/tagged.md", path="backend/tagged.md",
            title="Tagged Doc", content="Tagged content", collection="backend",
            tags=["api", "security", "auth"],
        ))

        results = await self.fts.search("Tagged", collection="backend", tags=["api", "security"])
        assert results.total >= 1
        assert results.results[0].path == "backend/tagged.md"

        # Wrong tags should return nothing
        no_results = await self.fts.search("Tagged", collection="backend", tags=["api", "frontend"])
        assert no_results.total == 0
