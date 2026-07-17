"""Tests for Leiden clustering + LLM naming layer."""

from unittest.mock import AsyncMock, patch

import pytest

from app.domain.codebase.generation.leiden_clustering import (
    _fallback_name,
    _run_leiden,
    recommend_wiki_outline,
)


class TestLeidenClustering:
    async def test_run_leiden_triangle(self):
        """A fully connected triangle clusters into one community."""
        edges = [(1, 2, 1.0), (2, 3, 1.0), (1, 3, 1.0)]
        result = await _run_leiden(edges)
        assert result is not None
        communities = set(result.values())
        assert len(communities) == 1
        assert result[1] == result[2] == result[3]

    async def test_run_leiden_two_communities(self):
        """Two disconnected triangles form two communities."""
        edges = [
            (1, 2, 1.0), (2, 3, 1.0), (1, 3, 1.0),   # group A
            (4, 5, 1.0), (5, 6, 1.0), (4, 6, 1.0),   # group B
        ]
        result = await _run_leiden(edges)
        assert result is not None
        communities = set(result.values())
        # Nodes 1,2,3 should share one community; 4,5,6 the other.
        assert result[1] == result[2] == result[3]
        assert result[4] == result[5] == result[6]
        assert result[1] != result[4]

    async def test_recommend_empty_when_no_data(self):
        """No CodeRelation data returns an empty outline."""
        mock_session = AsyncMock()

        class MockResult:
            def __init__(self, rows=None, repo_id=None):
                self._rows = rows or []
                self._repo_id = repo_id

            async def all(self):
                return self._rows

            async def scalar_one_or_none(self):
                return self._repo_id

        mock_session.execute.return_value = MockResult(repo_id=None)  # no repo found

        result = await recommend_wiki_outline(1, mock_session)
        assert result == []

    def test_fallback_name_with_dotted_names(self):
        """_fallback_name extracts common prefixes from dotted names."""
        cluster = {
            "entity_names": ["auth.login", "auth.logout", "auth.register", "user.profile"],
        }
        name = _fallback_name(cluster)
        # "auth" is the most common first part
        assert "auth" in name.lower() or "user" in name.lower()

    def test_fallback_name_empty(self):
        """_fallback_name returns 'Other' for empty names."""
        assert _fallback_name({"entity_names": []}) == "Other"
