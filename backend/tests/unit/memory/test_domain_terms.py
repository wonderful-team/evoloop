"""
Unit tests for DomainTermBank (v3 — LLM-driven, no regex/n-gram).

Run with: pytest tests/unit/memory/test_domain_terms.py -v
"""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.core.memory.domain_terms import DomainTermBank, TermMeta


@pytest.fixture
def temp_term_bank():
    """Create a DomainTermBank backed by a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bank = DomainTermBank(base_path=tmpdir)
        # Mock LLM extraction to avoid requiring real LLM config in tests
        bank._extract_with_llm = AsyncMock(return_value=[])
        yield bank


class TestTermMeta:
    """Tests for the lightweight TermMeta class."""

    def test_round_trip(self):
        meta = TermMeta(freq=5)
        d = meta.to_dict()
        assert d["freq"] == 5
        assert "last_seen" in d
        assert "confidence" not in d
        assert "lang" not in d
        assert "aliases" not in d

        restored = TermMeta.from_dict(d)
        assert restored.freq == 5


class TestPersistence:
    """Tests for JSON read/write."""

    async def test_save_and_load(self, temp_term_bank):
        bank = temp_term_bank
        terms = {
            "api": TermMeta(freq=5),
            "函数": TermMeta(freq=3),
        }
        await bank._save(project_id=42, terms=terms)
        loaded = await bank._load(project_id=42)

        assert "api" in loaded
        assert loaded["api"].freq == 5
        assert "函数" in loaded

    async def test_file_format_is_compact(self, temp_term_bank):
        """Verify no bloat fields like 'updated_at', 'lang', 'aliases', 'confidence'."""
        bank = temp_term_bank
        terms = {"test": TermMeta(freq=1)}
        await bank._save(project_id=1, terms=terms)

        path = bank._project_path(1)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert "updated_at" not in raw
        assert "terms" in raw
        term_data = raw["terms"]["test"]
        assert "lang" not in term_data
        assert "aliases" not in term_data
        assert "confidence" not in term_data
        assert "freq" in term_data
        assert "last_seen" in term_data


class TestDiscover:
    """Tests for LLM-driven discover."""

    async def test_discover_persists_terms_immediately(self, temp_term_bank):
        """v3: no staging, terms are persisted immediately upon LLM extraction."""
        bank = temp_term_bank
        bank._extract_with_llm = AsyncMock(return_value=["api", "gateway", "jwt"])

        await bank.discover("The API Gateway uses JWT.", project_id=1)
        terms = await bank.get_terms(project_id=1)
        assert "api" in terms
        assert "gateway" in terms
        assert "jwt" in terms
        assert terms["api"].freq == 1

    async def test_discover_increments_freq_on_repeat(self, temp_term_bank):
        bank = temp_term_bank
        bank._extract_with_llm = AsyncMock(return_value=["api"])

        await bank.discover("API content", project_id=1)
        await bank.discover("API content again", project_id=1)
        terms = await bank.get_terms(project_id=1)
        assert terms["api"].freq == 2

    async def test_discover_passes_project_context(self, temp_term_bank):
        bank = temp_term_bank
        mock = AsyncMock(return_value=["术语"])
        bank._extract_with_llm = mock

        await bank.discover("content", project_id=1, project_context="Project: PTE")
        mock.assert_awaited_once()
        args, _ = mock.call_args
        # _extract_with_llm is a mock (no self binding), so args = (content, project_context)
        assert args[0] == "content"
        assert args[1] == "Project: PTE"

    async def test_discover_empty_content(self, temp_term_bank):
        bank = temp_term_bank
        bank._extract_with_llm = AsyncMock(return_value=["x"])
        result = await bank.discover("", project_id=1)
        bank._extract_with_llm.assert_not_awaited()
        assert result == []

    async def test_discover_whitespace_only(self, temp_term_bank):
        bank = temp_term_bank
        result = await bank.discover("   \n\t  ", project_id=1)
        bank._extract_with_llm.assert_not_awaited()
        assert result == []


class TestMatch:
    """Tests for term matching."""

    async def test_match_known_terms(self, temp_term_bank):
        bank = temp_term_bank
        terms = {
            "api": TermMeta(freq=2),
            "gateway": TermMeta(freq=2),
            "jwt": TermMeta(freq=1),
        }
        await bank._save(project_id=1, terms=terms)

        matched = await bank.match("We need to update the API Gateway config.", project_id=1)
        assert "api" in matched
        assert "gateway" in matched
        assert "jwt" not in matched

    async def test_match_empty_bank(self, temp_term_bank):
        bank = temp_term_bank
        matched = await bank.match("API Gateway", project_id=99)
        assert matched == []

    async def test_match_fallback_to_global(self, temp_term_bank):
        bank = temp_term_bank
        global_terms = {"global_term": TermMeta(freq=5)}
        await bank._save(project_id=None, terms=global_terms)

        matched = await bank.match("text with global_term", project_id=99)
        assert "global_term" in matched


class TestDecay:
    """Tests for temporal decay."""

    async def test_decay_removes_stale_terms(self, temp_term_bank):
        bank = temp_term_bank
        old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        terms = {
            "stale": TermMeta(freq=1, last_seen=old_time),
            "fresh": TermMeta(freq=10, last_seen=datetime.now(timezone.utc)),
        }
        await bank._save(project_id=1, terms=terms)

        removed = await bank.decay(project_id=1, half_life_days=30)
        assert "stale" in removed

        survivors = await bank.get_terms(project_id=1)
        assert "fresh" in survivors
        assert "stale" not in survivors

    async def test_decay_computes_confidence_at_runtime(self, temp_term_bank):
        bank = temp_term_bank
        recent = datetime.now(timezone.utc)
        terms = {"recent": TermMeta(freq=5, last_seen=recent)}
        await bank._save(project_id=1, terms=terms)

        await bank.decay(project_id=1, half_life_days=1)
        loaded = await bank.get_terms(project_id=1)
        assert "recent" in loaded


class TestTopTerms:
    """Tests for get_top_terms ranking."""

    async def test_ranking_by_freq(self, temp_term_bank):
        bank = temp_term_bank
        recent = datetime.now(timezone.utc)
        terms = {
            "rare": TermMeta(freq=1, last_seen=recent),
            "common": TermMeta(freq=100, last_seen=recent),
            "medium": TermMeta(freq=10, last_seen=recent),
        }
        await bank._save(project_id=1, terms=terms)

        top = await bank.get_top_terms(project_id=1, limit=2)
        assert len(top) == 2
        assert "common" in top

    async def test_respects_min_confidence(self, temp_term_bank):
        bank = temp_term_bank
        recent = datetime.now(timezone.utc)
        old = datetime.now(timezone.utc) - timedelta(days=30)
        terms = {
            "high": TermMeta(freq=10, last_seen=recent),
            "low": TermMeta(freq=1, last_seen=old),
        }
        await bank._save(project_id=1, terms=terms)

        top = await bank.get_top_terms(project_id=1, min_confidence=0.3)
        assert "high" in top
        assert "low" not in top


class TestCrossProjectIsolation:
    """Terms are isolated per project; global fallback works."""

    async def test_medical_vs_legal_isolation(self, temp_term_bank):
        bank = temp_term_bank

        # Seed project 1 (medical)
        await bank._save(project_id=1, terms={
            "心室颤动": TermMeta(freq=5),
            "心房扑动": TermMeta(freq=3),
        })

        # Seed project 2 (legal)
        await bank._save(project_id=2, terms={
            "不可抗力": TermMeta(freq=4),
            "违约责任": TermMeta(freq=3),
        })

        med_terms = await bank.get_terms(project_id=1)
        legal_terms = await bank.get_terms(project_id=2)

        assert "心室颤动" in med_terms
        assert "不可抗力" in legal_terms
        assert "心室颤动" not in legal_terms
        assert "不可抗力" not in med_terms

    async def test_global_fallback(self, temp_term_bank):
        bank = temp_term_bank

        # Seed global terms
        await bank._save(project_id=None, terms={
            "api": TermMeta(freq=5),
            "数据库": TermMeta(freq=3),
        })

        # New project without its own terms should see global
        match = await bank.match("This API uses async processing", project_id=999)
        assert "api" in match
        match_cn = await bank.match("这个API使用了数据库和缓存", project_id=999)
        assert "数据库" in match_cn


class TestConcurrency:
    """Multiple concurrent discoveries must not lose data."""

    async def test_concurrent_discover_no_data_loss(self, temp_term_bank):
        bank = temp_term_bank
        project_id = 7

        # Each call extracts the same terms
        bank._extract_with_llm = AsyncMock(return_value=["api", "gateway", "jwt"])

        contents = [f"Module {i} uses API Gateway for routing and JWT for auth." for i in range(20)]
        await asyncio.gather(*[
            bank.discover(c, project_id=project_id)
            for c in contents
        ])

        terms = await bank.get_terms(project_id)
        assert "api" in terms
        assert terms["api"].freq == 20
        assert "gateway" in terms
        assert "jwt" in terms


class TestComputeConfidence:
    """Tests for the static confidence computation formula."""

    def test_high_freq_recent(self):
        recent = datetime.now(timezone.utc)
        c = DomainTermBank._compute_confidence(20, recent)
        assert c == 0.95  # capped at 0.95

    def test_low_freq_old(self):
        old = datetime.now(timezone.utc) - timedelta(days=60)
        c = DomainTermBank._compute_confidence(1, old)
        assert c < 0.15  # below minimum threshold

    def test_mid_freq_mid_age(self):
        mid = datetime.now(timezone.utc) - timedelta(days=30)
        c = DomainTermBank._compute_confidence(5, mid)
        assert 0.2 < c < 0.5


class TestParseLLMResponse:
    """Tests for JSON parsing from LLM responses."""

    def test_simple_json_array(self):
        bank = DomainTermBank("/tmp/fake")
        terms = bank._parse_llm_response('```json\n["api", "gateway"]\n```')
        assert terms == ["api", "gateway"]

    def test_plain_array(self):
        bank = DomainTermBank("/tmp/fake")
        terms = bank._parse_llm_response('["term1", "term2"]')
        assert terms == ["term1", "term2"]

    def test_invalid_json(self):
        bank = DomainTermBank("/tmp/fake")
        terms = bank._parse_llm_response("not json")
        assert terms == []

    def test_non_string_items_filtered(self):
        bank = DomainTermBank("/tmp/fake")
        terms = bank._parse_llm_response('["valid", 123, null, "also valid"]')
        assert terms == ["valid", "also valid"]
