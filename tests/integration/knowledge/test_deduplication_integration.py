"""
Deduplication integration tests with real documents and real MinHash LSH.

No mocks.
"""

import pytest

from app.domain.knowledge.models import MarkdownDocument
from app.domain.knowledge.services.deduplication import DeduplicationService
from app.domain.knowledge.services.store import KnowledgeStoreService


class TestDeduplicationIntegration:
    """Real duplicate detection on real stored documents."""

    @pytest.fixture(autouse=True)
    def setup(self, temp_knowledge_dir):
        self.store = KnowledgeStoreService(base_path=str(temp_knowledge_dir))
        self.service = DeduplicationService(store=self.store)

    def test_exact_duplicate_detection(self):
        """Two identical documents are flagged as exact duplicates."""
        content = "This is exactly the same content for both documents."
        doc = MarkdownDocument(content=content, source="a.txt", mime_type="text/plain")

        self.store.save_document(doc, collection="dup", path="doc1.md")
        self.store.save_document(doc, collection="dup", path="doc2.md")

        import asyncio
        report = asyncio.run(self.service.analyze_project("dup"))

        assert report.total_documents == 2
        assert len(report.exact_duplicates) >= 1

    def test_near_duplicate_detection(self):
        """Very similar documents are grouped by LSH."""
        doc1 = MarkdownDocument(
            content="FastAPI is a modern web framework for building APIs with Python 3.",
            source="a.txt", mime_type="text/plain"
        )
        doc2 = MarkdownDocument(
            content="FastAPI is a modern web framework for building APIs with Python 3 quickly.",
            source="b.txt", mime_type="text/plain"
        )
        doc3 = MarkdownDocument(
            content="Completely unrelated topic about kubernetes deployment strategies.",
            source="c.txt", mime_type="text/plain"
        )

        self.store.save_document(doc1, collection="near", path="a.md")
        self.store.save_document(doc2, collection="near", path="b.md")
        self.store.save_document(doc3, collection="near", path="c.md")

        import asyncio
        report = asyncio.run(self.service.analyze_project("near"))

        assert report.total_documents == 3
        # doc1 and doc2 should be in a similar group
        all_grouped = set()
        for group in report.similar_documents:
            all_grouped.update(group)

        # At least a.md and b.md should be detected as similar
        assert "near/a.md" in all_grouped
        assert "near/b.md" in all_grouped
        assert "near/c.md" not in all_grouped

    def test_find_similar_to_new_document(self):
        """find_similar finds existing docs similar to new content."""
        doc = MarkdownDocument(
            content="Python web framework FastAPI tutorial guide",
            source="existing.txt", mime_type="text/plain"
        )
        self.store.save_document(doc, collection="find", path="existing.md")

        import asyncio
        results = asyncio.run(self.service.find_similar(
            title="FastAPI Guide",
            content="FastAPI is a modern Python web framework for APIs",
            project="find",
            threshold=0.5,
        ))

        assert len(results) >= 1
        assert any("existing.md" in r.path for r in results)

    def test_no_false_positives_for_unrelated(self):
        """Unrelated documents are not flagged as similar."""
        doc1 = MarkdownDocument(content="Blockchain cryptocurrency decentralized ledger technology", source="a.txt", mime_type="text/plain")
        doc2 = MarkdownDocument(content="Machine learning neural networks deep learning AI models", source="b.txt", mime_type="text/plain")

        self.store.save_document(doc1, collection="unrel", path="a.md")
        self.store.save_document(doc2, collection="unrel", path="b.md")

        import asyncio
        report = asyncio.run(self.service.analyze_project("unrel"))

        assert report.total_documents == 2
        # No exact duplicates
        assert len(report.exact_duplicates) == 0
        # No similar groups (threshold 0.8 is high)
        assert len(report.similar_documents) == 0
