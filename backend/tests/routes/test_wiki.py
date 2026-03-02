"""
Tests for wiki routes.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestListWikiPages:
    """Tests for listing wiki pages."""

    def test_list_pages(self, client, auth_headers, mock_current_user):
        """Test listing wiki pages for a project."""
        from datetime import datetime
        with patch("app.api.routes.wiki.wiki_service") as mock_service:
            mock_service.get_pages = MagicMock(return_value=[
                {
                    "id": 1,
                    "project_id": 1,
                    "title": "Page 1",
                    "slug": "page-1",
                    "content": "Content 1",
                    "parent_id": None,
                    "order": 0,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                },
                {
                    "id": 2,
                    "project_id": 1,
                    "title": "Page 2",
                    "slug": "page-2",
                    "content": "Content 2",
                    "parent_id": None,
                    "order": 1,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                },
            ])

            response = client.get("/api/v1/wiki/1", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["title"] == "Page 1"

    def test_list_pages_empty(self, client, auth_headers, mock_current_user):
        """Test listing wiki pages when none exist."""
        with patch("app.api.routes.wiki.wiki_service") as mock_service:
            mock_service.get_pages = MagicMock(return_value=[])

            response = client.get("/api/v1/wiki/1", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data == []


class TestGenerateWiki:
    """Tests for wiki generation."""

    def test_generate_wiki(self, client, auth_headers, mock_current_user):
        """Test triggering wiki generation."""
        with patch("app.domain.wiki.tasks.generate_wiki_task") as mock_task:
            mock_task.delay = MagicMock(return_value=MagicMock(id="task-123"))

            response = client.post(
                "/api/v1/wiki/generate",
                headers=auth_headers,
                json={
                    "project_id": 1,
                    "topic": "Test Topic",
                    "force_regenerate": False,
                },
            )
            assert response.status_code in [200, 201]
            data = response.json()
            assert data["status"] == "accepted"
            assert "task_id" in data

    def test_generate_wiki_error(self, client, auth_headers, mock_current_user):
        """Test wiki generation when task fails."""
        with patch("app.domain.wiki.tasks.generate_wiki_task") as mock_task:
            mock_task.delay = MagicMock(side_effect=Exception("Celery error"))

            response = client.post(
                "/api/v1/wiki/generate",
                headers=auth_headers,
                json={
                    "project_id": 1,
                    "topic": "Test Topic",
                },
            )
            assert response.status_code == 500
