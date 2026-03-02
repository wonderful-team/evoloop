"""
Unit tests for Wiki Service.
"""

import pytest
from unittest.mock import patch, MagicMock, mock_open, AsyncMock
import json

from app.domain.wiki.service import WikiService, wiki_service


class TestWikiService:
    """Tests for WikiService class."""

    @pytest.fixture
    def service(self):
        """Create WikiService instance."""
        return WikiService()

    def test_get_pages(self, service):
        """Test getting wiki pages."""
        with patch('app.domain.wiki.service.Session') as mock_session_class:
            mock_session = MagicMock()
            mock_page1 = MagicMock()
            mock_page1.title = "Page 1"
            mock_page2 = MagicMock()
            mock_page2.title = "Page 2"

            mock_result = MagicMock()
            mock_result.all.return_value = [mock_page1, mock_page2]
            mock_session.exec.return_value = mock_result
            mock_session_class.return_value.__enter__.return_value = mock_session

            result = service.get_pages(project_id=1)

            assert len(result) == 2
            assert result[0].title == "Page 1"
            assert result[1].title == "Page 2"

    def test_get_page_by_id(self, service):
        """Test getting a single page by ID."""
        with patch('app.domain.wiki.service.Session') as mock_session_class:
            mock_session = MagicMock()
            mock_page = MagicMock()
            mock_page.title = "Test Page"
            mock_session.get.return_value = mock_page
            mock_session_class.return_value.__enter__.return_value = mock_session

            result = service.get_page(page_id=1)

            assert result is not None
            assert result.title == "Test Page"
            # Verify get was called with correct page_id
            mock_session.get.assert_called_once()

    def test_get_page_not_found(self, service):
        """Test getting non-existent page."""
        with patch('app.domain.wiki.service.Session') as mock_session_class:
            mock_session = MagicMock()
            mock_session.get.return_value = None
            mock_session_class.return_value.__enter__.return_value = mock_session

            result = service.get_page(page_id=999)

            assert result is None

    def test_get_projects_with_wiki(self, service):
        """Test getting projects that have wiki pages."""
        with patch('app.domain.wiki.service.Session') as mock_session_class:
            mock_session = MagicMock()
            mock_session.exec.return_value.all.return_value = [1, 2, 3]
            mock_session_class.return_value.__enter__.return_value = mock_session

            result = service.get_projects_with_wiki([1, 2, 3, 4, 5])

            assert result == {1, 2, 3}

    def test_get_projects_with_wiki_empty_input(self, service):
        """Test getting projects with empty input."""
        result = service.get_projects_with_wiki([])
        assert result == set()

    def test_paths_to_tree_string(self, service):
        """Test converting paths to tree string."""
        paths = [
            "src/main.py",
            "src/utils/helper.py",
            "tests/test_main.py"
        ]

        result = service._paths_to_tree_string(paths)

        assert "src/" in result
        assert "main.py" in result
        assert "utils/" in result
        assert "helper.py" in result
        assert "tests/" in result
        assert "test_main.py" in result

    def test_paths_to_tree_string_empty(self, service):
        """Test converting empty paths list."""
        result = service._paths_to_tree_string([])
        assert result == ""

    def test_paths_to_tree_string_truncation(self, service):
        """Test tree string truncation at 5000 lines."""
        paths = [f"file{i}.txt" for i in range(5100)]

        result = service._paths_to_tree_string(paths)

        assert "... (truncated)" in result

    def test_read_file_safe_success(self, service):
        """Test reading file safely."""
        with patch('os.path.exists', return_value=True):
            with patch('os.path.isdir', return_value=False):
                with patch('builtins.open', mock_open(read_data="file content")):
                    result = service._read_file_safe("/path/to/file.txt")

                    assert result == "file content"

    def test_read_file_safe_not_exists(self, service):
        """Test reading non-existent file."""
        with patch('os.path.exists', return_value=False):
            result = service._read_file_safe("/path/to/missing.txt")

            assert result == ""

    def test_read_file_safe_is_directory(self, service):
        """Test reading a directory."""
        with patch('os.path.exists', return_value=True):
            with patch('os.path.isdir', return_value=True):
                result = service._read_file_safe("/path/to/dir")

                assert result == ""

    def test_read_file_safe_with_max_chars(self, service):
        """Test reading file with character limit."""
        with patch('os.path.exists', return_value=True):
            with patch('os.path.isdir', return_value=False):
                m = mock_open(read_data="a" * 100000)
                with patch('builtins.open', m):
                    result = service._read_file_safe("/path/to/file.txt", max_chars=1000)

                    # Should only read max_chars
                    assert len(result) <= 1000

    @pytest.mark.asyncio
    async def test_extract_and_store_concepts_disabled(self, service):
        """Test concept extraction when disabled."""
        with patch('app.domain.wiki.service.settings') as mock_settings:
            mock_settings.WIKI_EXTRACT_CONCEPTS = False

            result = await service._extract_and_store_concepts(
                page_title="Test",
                page_content="Content",
                project_id=1,
                llm=MagicMock()
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_extract_and_store_concepts_success(self, service):
        """Test successful concept extraction."""
        with patch('app.domain.wiki.service.settings') as mock_settings:
            mock_settings.WIKI_EXTRACT_CONCEPTS = True

            mock_llm = MagicMock()
            mock_structured = MagicMock()
            mock_result = MagicMock()
            mock_concept = MagicMock()
            mock_concept.name = "TestConcept"
            mock_concept.description = "A test concept"
            mock_result.concepts = [mock_concept]
            mock_structured.ainvoke = AsyncMock(return_value=mock_result)
            mock_llm.with_structured_output.return_value = mock_structured

            with patch('app.domain.wiki.service.memory_manager') as mock_memory:
                mock_memory.long_term.store_concept = AsyncMock(return_value=None)

                result = await service._extract_and_store_concepts(
                    page_title="Test",
                    page_content="Content",
                    project_id=1,
                    llm=mock_llm
                )

                assert len(result) == 1
                assert result[0] == "TestConcept"

    @pytest.mark.asyncio
    async def test_validate_structure_complete(self, service):
        """Test validating complete structure."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "is_complete": True,
            "gaps": []
        })
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        structure_data = {"pages": [{"title": "Page 1"}]}

        result = await service._validate_structure(
            structure_data=structure_data,
            project_context="Context",
            llm=mock_llm
        )

        assert result == structure_data

    @pytest.mark.asyncio
    async def test_validate_structure_with_gaps(self, service):
        """Test validating structure with gaps."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "is_complete": False,
            "gaps": [
                {"suggested_title": "Missing Page", "reason": "Needs documentation"}
            ]
        })
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        structure_data = {"pages": [{"title": "Page 1"}]}

        result = await service._validate_structure(
            structure_data=structure_data,
            project_context="Context",
            llm=mock_llm
        )

        assert len(result["pages"]) == 2
        assert result["pages"][1]["title"] == "Missing Page"

    @pytest.mark.asyncio
    async def test_validate_structure_invalid_json(self, service):
        """Test validating structure with invalid JSON response."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Not valid JSON"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        structure_data = {"pages": [{"title": "Page 1"}]}

        result = await service._validate_structure(
            structure_data=structure_data,
            project_context="Context",
            llm=mock_llm
        )

        # Should return original structure
        assert result == structure_data

    def test_global_wiki_service_instance(self):
        """Test that wiki_service is a singleton instance."""
        from app.domain.wiki.service import wiki_service
        assert isinstance(wiki_service, WikiService)
