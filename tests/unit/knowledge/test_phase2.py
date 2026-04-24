"""
Phase 2 Tests - Generalization & Search Enhancement

Covers:
- T-2.1: Configurable tag taxonomy (DB-driven + bilingual)
- T-2.2: Chinese tokenization via jieba query preprocessing
- T-2.3: MinHash LSH deduplication (O(n²) → O(n))
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.domain.knowledge.services.search import FTSService, IndexDocumentRequest
from app.domain.knowledge.services.auto_tagger import AutoTaggerService, _DEFAULT_TAG_CATEGORIES
from app.domain.knowledge.services.deduplication import (
    DeduplicationService,
    MinHash,
    LSH,
)


# ---------------------------------------------------------------------------
# T-2.1: Configurable Tag Taxonomy
# ---------------------------------------------------------------------------

class TestTagConfigDB:
    """T-2.1: tag_config table and CRUD operations"""

    def test_tag_config_table_created(self):
        db_path = Path(tempfile.mktemp(suffix=".db"))
        fts = FTSService(db_path=db_path)
        asyncio.run(fts.initialize())

        with fts.pool.acquire() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tag_config'"
            ).fetchone()
            assert row is not None
            assert row["name"] == "tag_config"

    def test_tag_config_crud(self):
        db_path = Path(tempfile.mktemp(suffix=".db"))
        fts = FTSService(db_path=db_path)
        asyncio.run(fts.initialize())

        # Create
        asyncio.run(fts.update_tag_config("rust", "tech", enabled=True, priority=10))
        asyncio.run(fts.update_tag_config("区块链", "domain", enabled=True, priority=5, description="blockchain"))
        asyncio.run(fts.update_tag_config("archived", "priority", enabled=False))

        # Read
        tags = fts.get_tag_config()
        enabled_tags = [t["tag"] for t in tags]

        assert "rust" in enabled_tags
        assert "区块链" in enabled_tags
        assert "archived" not in enabled_tags  # disabled

        # Update (change category)
        asyncio.run(fts.update_tag_config("rust", "domain", enabled=True, priority=20))
        tags = fts.get_tag_config()
        rust = next(t for t in tags if t["tag"] == "rust")
        assert rust["category"] == "domain"
        assert rust["priority"] == 20


class TestAutoTaggerConfigurability:
    """T-2.1: AutoTaggerService loads tags from DB or falls back to defaults"""

    def test_auto_tagger_loads_from_db(self):
        db_path = Path(tempfile.mktemp(suffix=".db"))
        fts = FTSService(db_path=db_path)
        asyncio.run(fts.initialize())

        # Seed DB with custom tags
        asyncio.run(fts.update_tag_config("custom-tag", "type", enabled=True, priority=1))
        asyncio.run(fts.update_tag_config("another-tag", "tech", enabled=True, priority=2))

        tagger = AutoTaggerService(fts_service=fts)
        tagger._ensure_tags_loaded()

        assert "custom-tag" in tagger._all_valid_tags
        assert "another-tag" in tagger._all_valid_tags
        assert tagger._tag_categories["type"] == ["custom-tag"]
        assert tagger._tag_categories["tech"] == ["another-tag"]

    def test_auto_tagger_fallback_to_defaults(self):
        tagger = AutoTaggerService(fts_service=None)
        tagger._ensure_tags_loaded()

        # Should have default tags including bilingual ones
        assert "architecture" in tagger._all_valid_tags
        assert "架构" in tagger._all_valid_tags
        assert "安全" in tagger._all_valid_tags
        assert "critical" in tagger._all_valid_tags
        assert "紧急" in tagger._all_valid_tags

    def test_auto_tagger_validate_uses_loaded_tags(self):
        tagger = AutoTaggerService(fts_service=None)
        validated = tagger._validate_tags(["架构", "security", "x"])
        assert "架构" in validated
        assert "security" in validated
        # "x" is too short (len <= 2) so it should be rejected
        assert "x" not in validated

    def test_auto_tagger_suggest_bilingual(self):
        tagger = AutoTaggerService(fts_service=None)
        # Direct suggestion match for Chinese tag
        suggestions = asyncio.run(tagger.suggest_tags_for_query("认证"))
        assert "认证" in suggestions
        # Verify both Chinese and English variants are in the same category
        tagger._ensure_tags_loaded()
        domain_tags = tagger._tag_categories.get("domain", [])
        assert "认证" in domain_tags
        assert "authentication" in domain_tags


# ---------------------------------------------------------------------------
# T-2.2: Chinese Query Preprocessing
# ---------------------------------------------------------------------------

class TestChineseQueryPreprocessing:
    """T-2.2: jieba-based query preprocessing for FTS5"""

    def test_preprocess_chinese_query(self):
        fts = FTSService()
        result = fts._preprocess_query("中文搜索测试")
        # jieba segments into phrase searches of individual CJK chars
        assert " " in result
        assert '"' in result  # phrase search markers
        assert "中" in result
        assert "文" in result

    def test_preprocess_english_query_unchanged(self):
        fts = FTSService()
        query = "fastapi authentication"
        result = fts._preprocess_query(query)
        assert result == query

    def test_preprocess_mixed_query(self):
        fts = FTSService()
        result = fts._preprocess_query("FastAPI认证指南")
        # Should segment Chinese part but preserve English
        assert "FastAPI" in result
        assert " " in result  # spaces from segmentation

    def test_preprocess_fts5_syntax_preserved(self):
        fts = FTSService()
        queries = [
            '"exact phrase"',
            'term1 AND term2',
            'term1 OR term2',
            'term1 NOT term2',
            'prefix*',
            'NEAR/5(term1 term2)',
        ]
        for q in queries:
            assert fts._preprocess_query(q) == q, f"FTS5 query mutated: {q}"

    def test_preprocess_empty_query(self):
        fts = FTSService()
        assert fts._preprocess_query("") == ""
        assert fts._preprocess_query("   ") == "   "


class TestFTSTagFilterRegression:
    """Regression: FTS tag filter SQL parameter order bug."""

    def test_tag_filter_returns_correct_documents(self):
        """Tag filtering should not be affected by parameter order."""
        db_path = Path(tempfile.mktemp(suffix=".db"))
        fts = FTSService(db_path=db_path)
        asyncio.run(fts.initialize())

        # Index doc with tags
        asyncio.run(fts.index_document(IndexDocumentRequest(
            doc_id="a/tagged.md",
            path="a/tagged.md",
            title="Tagged Doc",
            content="Tagged content here",
            collection="a",
            tags=["api", "security", "auth"],
        )))

        # Index doc without matching tags
        asyncio.run(fts.index_document(IndexDocumentRequest(
            doc_id="a/other.md",
            path="a/other.md",
            title="Other",
            content="Other content",
            collection="a",
            tags=["frontend", "ui"],
        )))

        # Search with tags that only match tagged.md
        results = asyncio.run(fts.search("Tagged", collection="a", tags=["api", "security"]))
        assert results.total == 1
        assert results.results[0].path == "a/tagged.md"

        # Wrong tags should return nothing
        no_results = asyncio.run(fts.search("Tagged", collection="a", tags=["api", "frontend"]))
        assert no_results.total == 0


# ---------------------------------------------------------------------------
# T-2.3: MinHash LSH Deduplication
# ---------------------------------------------------------------------------

class TestMinHash:
    """T-2.3: MinHash signature generation"""

    def test_signature_consistency(self):
        mh = MinHash(num_perm=64, shingle_size=3)
        sig1 = mh.signature("hello world this is a test document")
        sig2 = mh.signature("hello world this is a test document")
        assert sig1 == sig2
        assert len(sig1) == 64

    def test_similar_texts_have_similar_signatures(self):
        mh = MinHash(num_perm=128, shingle_size=3)
        text1 = "fastapi is a modern web framework for building apis"
        text2 = "fastapi is a modern web framework for building apis quickly"

        sig1 = mh.signature(text1)
        sig2 = mh.signature(text2)

        # Jaccard-like similarity: count matching bands
        matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
        similarity = matches / len(sig1)
        # Very similar texts should have >0.5 signature match
        assert similarity > 0.5

    def test_different_texts_have_different_signatures(self):
        mh = MinHash(num_perm=128, shingle_size=3)
        sig1 = mh.signature("python programming tutorial for beginners")
        sig2 = mh.signature("kubernetes deployment strategies in production")

        matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
        similarity = matches / len(sig1)
        # Very different texts should have low signature match
        assert similarity < 0.3


class TestLSH:
    """T-2.3: LSH bucket-based candidate generation"""

    def test_candidate_pairs_for_similar_docs(self):
        mh = MinHash(num_perm=128, shingle_size=3)
        lsh = LSH(num_perm=128, num_bands=16)

        doc1 = "fastapi guide for building rest apis with python"
        doc2 = "fastapi guide for building rest apis with python quickly"
        doc3 = "completely unrelated topic about blockchain technology"

        lsh.add("doc1", mh.signature(doc1))
        lsh.add("doc2", mh.signature(doc2))
        lsh.add("doc3", mh.signature(doc3))

        pairs = lsh.candidate_pairs()
        assert ("doc1", "doc2") in pairs or ("doc2", "doc1") in pairs
        # doc3 should not pair with doc1/doc2
        assert not any("doc3" in p for p in pairs)

    def test_no_false_negatives_for_exact_duplicates(self):
        mh = MinHash(num_perm=64, shingle_size=3)
        lsh = LSH(num_perm=64, num_bands=8)

        text = "duplicate document content exactly the same"
        sig = mh.signature(text)

        for i in range(5):
            lsh.add(f"doc_{i}", sig)

        pairs = lsh.candidate_pairs()
        # All 5 exact duplicates should produce candidate pairs
        assert len(pairs) >= 1


class TestDeduplicationLSH:
    """T-2.3: DeduplicationService uses MinHash LSH for analyze_project"""

    def test_find_similar_lsh_groups_similar_docs(self):
        service = DeduplicationService()

        doc_contents = {
            "a.md": "fastapi is a modern web framework for building apis with python",
            "b.md": "fastapi is a modern web framework for building apis with python quickly",
            "c.md": "completely different document about kubernetes and docker deployment",
            "d.md": "fastapi is a modern web framework for building rest apis with python language",
        }

        groups = asyncio.run(service._find_similar_lsh(doc_contents, threshold=0.5))

        # a, b, d are about fastapi/python and should be grouped
        all_grouped = set()
        for g in groups:
            all_grouped.update(g)

        assert "a.md" in all_grouped
        assert "b.md" in all_grouped
        assert "d.md" in all_grouped
        assert "c.md" not in all_grouped  # unrelated

    def test_find_similar_lsh_empty_input(self):
        service = DeduplicationService()
        groups = asyncio.run(service._find_similar_lsh({}, threshold=0.8))
        assert groups == []

    def test_find_similar_lsh_single_doc(self):
        service = DeduplicationService()
        groups = asyncio.run(service._find_similar_lsh({"only.md": "solo document"}, threshold=0.8))
        assert groups == []

    def test_sequence_matcher_offloaded(self):
        """Verify that _similarity_score is called via asyncio.to_thread in find_similar."""
        service = DeduplicationService()
        # Mock store to return a single document
        mock_doc = MagicMock()
        mock_doc.path = "test.md"
        mock_doc.title = "Test"

        mock_result = MagicMock()
        mock_result.content = "test content"

        with patch.object(service.store, "list_documents", return_value=[mock_doc]):
            with patch.object(service.store, "read_document", return_value=mock_result):
                with patch("app.domain.knowledge.services.deduplication.asyncio.to_thread") as mock_to_thread:
                    # Mock to_thread to immediately return a low similarity
                    mock_to_thread.side_effect = lambda fn, *args: fn(*args)

                    asyncio.run(service.find_similar("Test", "different content entirely"))

                    # SequenceMatcher calls should go through to_thread
                    assert mock_to_thread.call_count >= 1
