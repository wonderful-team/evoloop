"""
Unit tests for Retrieval Service.
Tests code search and entity relation retrieval.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.domain.codebase.retrieval.service import RetrievalService


class TestRetrievalService:
    """Tests for RetrievalService class."""

    @pytest.fixture
    def retrieval_service(self):
        """Create a RetrievalService instance with mocked embedder."""
        with patch("app.domain.codebase.retrieval.service.EmbedderFactory") as mock_factory:
            mock_embedder = MagicMock()
            mock_factory.get_embedder.return_value = mock_embedder
            yield RetrievalService(embedder=mock_embedder)

    @pytest.mark.asyncio
    async def test_search_with_project_id(self, retrieval_service):
        """Test search with explicit project_id."""
        with patch("app.domain.codebase.retrieval.hybrid.hybrid_searcher") as mock_searcher:
            mock_searcher.search = AsyncMock(return_value=[
                {"id": 1, "content": "def test(): pass", "score": 0.95}
            ])

            result = await retrieval_service.search("test function", project_id=1, limit=5)

            assert len(result) == 1
            assert result[0]["content"] == "def test(): pass"
            mock_searcher.search.assert_called_once_with("test function", project_id=1, limit=5)

    @pytest.mark.asyncio
    async def test_search_with_context_project_id(self, retrieval_service):
        """Test search using project_id from context."""
        with patch("app.domain.codebase.retrieval.service.ContextManager") as mock_ctx_manager:
            mock_ctx = MagicMock()
            mock_ctx.project_id = 42
            mock_ctx_manager.current.return_value = mock_ctx

            with patch("app.domain.codebase.retrieval.hybrid.hybrid_searcher") as mock_searcher:
                mock_searcher.search = AsyncMock(return_value=[])

                await retrieval_service.search("query", limit=10)

                mock_searcher.search.assert_called_once_with("query", project_id=42, limit=10)

    @pytest.mark.asyncio
    async def test_search_empty_results(self, retrieval_service):
        """Test search returning empty results."""
        with patch("app.domain.codebase.retrieval.hybrid.hybrid_searcher") as mock_searcher:
            mock_searcher.search = AsyncMock(return_value=[])

            result = await retrieval_service.search("nonexistent", project_id=1)

            assert result == []

    @pytest.mark.asyncio
    async def test_get_entity_relations_found(self, retrieval_service):
        """Test getting relations for existing entity."""
        mock_entity = MagicMock()
        mock_entity.id = 1
        mock_entity.full_name = "module.Class.method"
        mock_entity.type = "function"
        mock_entity.file.path = "/test/file.py"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_entity

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        # Mock outgoing relations
        mock_out_rel = MagicMock()
        mock_out_rel.relation_type = "calls"
        mock_out_target = MagicMock()
        mock_out_target.full_name = "other.Function"
        mock_out_rows = [(mock_out_rel, mock_out_target)]

        # Mock incoming relations
        mock_in_rel = MagicMock()
        mock_in_rel.relation_type = "inherits"
        mock_in_source = MagicMock()
        mock_in_source.full_name = "ParentClass"
        mock_in_rows = [(mock_in_rel, mock_in_source)]

        mock_session.execute.side_effect = [
            mock_result,  # First entity query
            MagicMock(all=lambda: mock_out_rows),  # Outgoing relations
            MagicMock(all=lambda: mock_in_rows),  # Incoming relations
        ]

        with patch.object(retrieval_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await retrieval_service.get_entity_relations("method", project_id=1)

            assert result["symbol"] == "module.Class.method"
            assert result["type"] == "function"
            assert len(result["relations"]["outgoing"]) == 1
            assert len(result["relations"]["incoming"]) == 1

    @pytest.mark.asyncio
    async def test_get_entity_relations_not_found(self, retrieval_service):
        """Test getting relations for non-existent entity."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with patch.object(retrieval_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await retrieval_service.get_entity_relations("nonexistent", project_id=1)

            assert "error" in result
            assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_entity_relations_fuzzy_match(self, retrieval_service):
        """Test fuzzy matching for entity relations."""
        # First query returns None (exact match fails)
        # Second query (fuzzy) returns entity
        mock_entity = MagicMock()
        mock_entity.id = 1
        mock_entity.full_name = "module.ClassName"
        mock_entity.type = "class"
        mock_entity.file.path = "/test/file.py"

        first_result = MagicMock()
        first_result.scalar_one_or_none.return_value = None

        second_result = MagicMock()
        second_result.scalar_one_or_none.return_value = mock_entity

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            first_result,  # Exact match - not found
            second_result,  # Fuzzy match - found
            MagicMock(all=lambda: []),  # Outgoing relations
            MagicMock(all=lambda: []),  # Incoming relations
        ]

        with patch.object(retrieval_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await retrieval_service.get_entity_relations("Class", project_id=1)

            assert result["symbol"] == "module.ClassName"

    @pytest.mark.asyncio
    async def test_get_entity_relations_without_project_id(self, retrieval_service):
        """Test getting relations without project_id filter."""
        mock_entity = MagicMock()
        mock_entity.id = 1
        mock_entity.full_name = "global.Function"
        mock_entity.type = "function"
        mock_entity.file.path = "/test/file.py"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_entity

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            mock_result,
            MagicMock(all=lambda: []),
            MagicMock(all=lambda: []),
        ]

        with patch.object(retrieval_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await retrieval_service.get_entity_relations("Function")

            assert result["symbol"] == "global.Function"


class TestRetrievalServiceEdgeCases:
    """Edge case tests for RetrievalService."""

    @pytest.fixture
    def retrieval_service(self):
        """Create a RetrievalService instance."""
        with patch("app.domain.codebase.retrieval.service.EmbedderFactory"):
            yield RetrievalService()

    @pytest.mark.asyncio
    async def test_get_entity_relations_target_entity_none(self, retrieval_service):
        """Test handling when target entity is None in relation."""
        mock_entity = MagicMock()
        mock_entity.id = 1
        mock_entity.full_name = "module.Function"
        mock_entity.type = "function"
        mock_entity.file.path = "/test/file.py"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_entity

        mock_session = AsyncMock()

        # Outgoing relation with None target (uses target_name instead)
        mock_out_rel = MagicMock()
        mock_out_rel.relation_type = "imports"
        mock_out_rel.target_name = "external.module"
        mock_out_target = None  # Target entity not found
        mock_out_rows = [(mock_out_rel, mock_out_target)]

        mock_session.execute.side_effect = [
            mock_result,
            MagicMock(all=lambda: mock_out_rows),
            MagicMock(all=lambda: []),
        ]

        with patch.object(retrieval_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await retrieval_service.get_entity_relations("Function")

            # Should use target_name when entity is None
            assert "external.module" in result["relations"]["outgoing"][0]
