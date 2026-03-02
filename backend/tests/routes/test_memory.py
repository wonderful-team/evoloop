"""
Tests for memory routes.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestListConcepts:
    """Tests for listing concepts."""

    def test_list_concepts(self, client):
        """Test listing all concepts for a project."""
        with patch("app.api.routes.memory.memory_manager") as mock_mm:
            mock_mm.long_term.search_concepts_data = AsyncMock(return_value=[
                {"name": "Concept 1", "description": "Description 1"},
                {"name": "Concept 2", "description": "Description 2"},
            ])

            response = client.get("/api/v1/memory/concepts?project_id=1")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["name"] == "Concept 1"

    def test_list_concepts_empty(self, client):
        """Test listing concepts when none exist."""
        with patch("app.api.routes.memory.memory_manager") as mock_mm:
            mock_mm.long_term.search_concepts_data = AsyncMock(return_value=[])

            response = client.get("/api/v1/memory/concepts?project_id=1")
            assert response.status_code == 200
            data = response.json()
            assert data == []


class TestListConceptsWithCounts:
    """Tests for listing concepts with episode counts."""

    def test_list_concepts_with_counts(self, client):
        """Test listing concepts with episode counts."""
        with patch("app.api.routes.memory.memory_manager") as mock_mm:
            mock_mm.long_term.list_concepts = AsyncMock(return_value=[
                {"name": "Concept 1", "description": "Description 1", "episode_count": 5},
                {"name": "Concept 2", "description": "Description 2", "episode_count": 3},
            ])

            response = client.get("/api/v1/memory/concepts/list?project_id=1")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["episode_count"] == 5


class TestAddConcept:
    """Tests for adding concepts."""

    def test_add_concept(self, client):
        """Test adding a new concept."""
        with patch("app.api.routes.memory.memory_manager") as mock_mm:
            mock_mm.long_term.store_concept = AsyncMock(return_value=None)

            response = client.post(
                "/api/v1/memory/concepts?project_id=1",
                json={
                    "name": "New Concept",
                    "description": "A new concept description",
                    "related_files": ["file1.py", "file2.py"],
                },
            )
            assert response.status_code in [200, 201]
            data = response.json()
            assert data["status"] == "success"
            assert data["name"] == "New Concept"

    def test_add_concept_error(self, client):
        """Test adding a concept when service fails."""
        with patch("app.api.routes.memory.memory_manager") as mock_mm:
            mock_mm.long_term.store_concept = AsyncMock(side_effect=Exception("Database error"))

            response = client.post(
                "/api/v1/memory/concepts?project_id=1",
                json={
                    "name": "New Concept",
                    "description": "A new concept description",
                },
            )
            assert response.status_code == 500


class TestSearchMemory:
    """Tests for searching memory."""

    def test_search_memory(self, client):
        """Test searching memory concepts."""
        with patch("app.api.routes.memory.memory_manager") as mock_mm:
            mock_mm.long_term.search_concepts_data = AsyncMock(return_value=[
                {"name": "Concept 1", "description": "Description 1"},
                {"name": "Concept 2", "description": "Description 2"},
            ])

            response = client.get("/api/v1/memory/search?q=test&project_id=1")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2

    def test_search_memory_empty_query(self, client):
        """Test searching with empty query."""
        response = client.get("/api/v1/memory/search?q=")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_search_memory_no_project(self, client):
        """Test searching without project_id."""
        with patch("app.api.routes.memory.memory_manager") as mock_mm:
            mock_mm.long_term.search_concepts_data = AsyncMock(return_value=[
                {"name": "Concept 1", "description": "Description 1"},
            ])

            response = client.get("/api/v1/memory/search?q=test")
            assert response.status_code == 200


class TestGetEpisodesByConcept:
    """Tests for getting episodes by concept."""

    def test_get_episodes_by_concept(self, client):
        """Test finding episodes by concept."""
        with patch("app.api.routes.memory.memory_manager") as mock_mm:
            mock_mm.long_term.find_episodes_by_concept = AsyncMock(return_value=[
                {"id": "ep-1", "goal": "Goal 1", "result": "Result 1", "error": None, "timestamp": 1234567890},
                {"id": "ep-2", "goal": "Goal 2", "result": "Result 2", "error": None, "timestamp": 1234567891},
            ])

            response = client.get("/api/v1/memory/episodes/by-concept?project_id=1&concept=Concept1")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["goal"] == "Goal 1"

    def test_get_episodes_empty_concept(self, client):
        """Test finding episodes with empty concept."""
        response = client.get("/api/v1/memory/episodes/by-concept?project_id=1&concept=")
        assert response.status_code == 200
        data = response.json()
        assert data == []
