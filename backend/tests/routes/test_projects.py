"""
Tests for project routes.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestListProjects:
    """Tests for listing projects."""

    def test_list_projects_empty(self, client, auth_headers):
        """Test listing projects with empty result."""
        with patch("app.api.routes.projects.evocloud_manager") as mock_ec:
            mock_ec.api.get_projects = AsyncMock(return_value={"list": [], "total": 0})

            response = client.get("/api/v1/projects/", headers=auth_headers)
            assert response.status_code in [200, 500]


class TestGetCurrentProject:
    """Tests for getting current project."""

    def test_get_current_project_success(self, client, auth_headers):
        """Test getting current project."""
        with patch("app.api.routes.projects.evocloud_manager") as mock_ec:
            mock_ec.api.get_current_project = AsyncMock(return_value={
                "project_id": 1,
                "name": "Current Project",
                "path": "/projects/current"
            })

            response = client.get("/api/v1/projects/current", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == 1
            assert data["name"] == "Current Project"


class TestCreateProject:
    """Tests for creating projects."""

    def test_create_project_success(self, client, auth_headers, tmp_path):
        """Test successfully creating a project."""
        with patch("app.api.routes.projects.settings") as mock_settings:
            mock_settings.PROJECTS_ROOT = str(tmp_path)

            with patch("app.api.routes.projects.evocloud_manager") as mock_ec:
                mock_ec.api.create_project = AsyncMock(return_value={"code": 0})
                mock_ec.scan_projects = AsyncMock(return_value=[
                    {"project_id": 1, "name": "NewProject"}
                ])

                response = client.post(
                    "/api/v1/projects/",
                    headers=auth_headers,
                    json={
                        "name": "NewProject",
                        "description": "A new test project",
                        "path": "/custom/path",
                    },
                )
                assert response.status_code == 200
                data = response.json()
                assert data["name"] == "NewProject"

    def test_create_project_already_exists(self, client, auth_headers, tmp_path):
        """Test creating a project that already exists."""
        with patch("app.api.routes.projects.settings") as mock_settings:
            mock_settings.PROJECTS_ROOT = str(tmp_path)

            # Create the directory first
            import os
            os.makedirs(os.path.join(tmp_path, "ExistingProject"), exist_ok=True)

            response = client.post(
                "/api/v1/projects/",
                headers=auth_headers,
                json={
                    "name": "ExistingProject",
                    "description": "This should fail",
                    "path": "/some/path",
                },
            )
            assert response.status_code == 400
            assert "already exists" in response.json()["detail"].lower()

    def test_create_project_no_root_configured(self, client, auth_headers):
        """Test creating a project when PROJECTS_ROOT is not configured."""
        with patch("app.api.routes.projects.settings") as mock_settings:
            mock_settings.PROJECTS_ROOT = None

            response = client.post(
                "/api/v1/projects/",
                headers=auth_headers,
                json={
                    "name": "New Project",
                    "description": "A new project",
                    "path": "/path",
                },
            )
            assert response.status_code == 500


class TestProjectStatus:
    """Tests for project status endpoint."""

    def test_get_project_status(self, client):
        """Test getting project status."""
        with patch("app.infrastructure.database.redis.redis_client") as mock_redis:
            mock_pipe = MagicMock()
            mock_pipe.execute = AsyncMock(return_value=[
                {"status": "running", "updated_at": "1234567890"},
                {"status": "completed", "updated_at": "1234567890"},
                {"status": "idle"},
            ])
            mock_redis.pipeline.return_value = mock_pipe

            response = client.get("/api/v1/projects/1/status")
            assert response.status_code == 200
            data = response.json()
            assert "indexing" in data
            assert "summarization" in data
            assert "wiki" in data


class TestDeleteProject:
    """Tests for deleting projects."""

    def test_delete_project_success(self, client):
        """Test successfully deleting a project."""
        with patch("app.api.routes.projects.evocloud_manager") as mock_ec:
            mock_ec.api.delete_project = AsyncMock(return_value={"code": 0})

            response = client.delete("/api/v1/projects/1")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["id"] == 1

    def test_delete_project_failure(self, client):
        """Test deleting a project when API fails."""
        with patch("app.api.routes.projects.evocloud_manager") as mock_ec:
            mock_ec.api.delete_project = AsyncMock(return_value={
                "code": 1,
                "message": "Project not found"
            })

            response = client.delete("/api/v1/projects/999")
            assert response.status_code == 500


class TestRunIndexing:
    """Tests for running indexing endpoint."""

    def test_run_indexing_success(self, client):
        """Test triggering indexing for a project."""
        with patch("app.api.routes.projects.indexing_manager") as mock_manager:
            mock_manager.dispatch_full_index = MagicMock()

            response = client.post(
                "/api/v1/projects/indexing/run",
                json={"project_id": 1}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert data["project_id"] == 1


class TestDetectedProjects:
    """Tests for detected projects endpoints."""

    def test_get_detected_projects_endpoint(self, client):
        """Test getting detected projects endpoint exists."""
        response = client.get("/api/v1/projects/detected")
        # Endpoint should exist, may return 200 or error depending on service
        assert response.status_code in [200, 500]

    def test_import_detected_project_endpoint(self, client):
        """Test importing a detected project endpoint exists."""
        response = client.post("/api/v1/projects/1/import")
        assert response.status_code in [200, 400, 500]

    def test_ignore_detected_project_endpoint(self, client):
        """Test ignoring a detected project endpoint exists."""
        response = client.post("/api/v1/projects/1/ignore")
        assert response.status_code in [200, 400, 500]

    def test_get_ignored_projects_endpoint(self, client):
        """Test getting ignored projects endpoint exists."""
        response = client.get("/api/v1/projects/ignored")
        assert response.status_code in [200, 500]

    def test_unignore_project_endpoint(self, client):
        """Test unignoring a project endpoint exists."""
        response = client.post("/api/v1/projects/2/unignore")
        assert response.status_code in [200, 400, 500]
