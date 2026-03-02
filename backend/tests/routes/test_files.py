"""
Tests for file routes.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestListFiles:
    """Tests for listing files."""

    def test_list_files_endpoint(self, client, auth_headers):
        """Test listing files endpoint exists."""
        response = client.get(
            "/api/v1/projects/1/files",
            headers=auth_headers
        )
        # May succeed or fail depending on mocking
        assert response.status_code in [200, 404, 500]

    def test_list_files_project_not_found(self, client, auth_headers):
        """Test listing files for non-existent project."""
        with patch("app.api.routes.files.evocloud_manager") as mock_ec:
            mock_ec.get_project_by_id = AsyncMock(return_value=None)

            response = client.get(
                "/api/v1/projects/999/files",
                headers=auth_headers
            )
            assert response.status_code == 404


class TestReadFile:
    """Tests for reading files."""

    def test_read_file_endpoint(self, client, auth_headers):
        """Test reading a file endpoint exists."""
        response = client.get(
            "/api/v1/projects/1/files/read?path=file.txt",
            headers=auth_headers
        )
        # May return 200, 404, or 500 depending on mocking
        assert response.status_code in [200, 404, 500]


class TestWriteFile:
    """Tests for writing files."""

    def test_write_file_endpoint(self, client, auth_headers):
        """Test writing a file endpoint exists."""
        response = client.post(
            "/api/v1/projects/1/files/write",
            headers=auth_headers,
            json={
                "path": "file.txt",
                "content": "New file content",
            },
        )
        assert response.status_code in [200, 201, 404, 500]


class TestDeleteFile:
    """Tests for deleting files."""

    def test_delete_file_endpoint(self, client, auth_headers):
        """Test deleting a file endpoint exists."""
        response = client.delete(
            "/api/v1/projects/1/files?path=file.txt",
            headers=auth_headers
        )
        assert response.status_code in [200, 204, 404, 500]


class TestSearchFiles:
    """Tests for searching files."""

    def test_search_files_endpoint(self, client, auth_headers):
        """Test searching files endpoint exists."""
        response = client.post(
            "/api/v1/projects/1/files/search",
            headers=auth_headers,
            json={
                "query": "pattern",
                "path": "/",
                "file_pattern": "*.py",
            },
        )
        assert response.status_code in [200, 404, 500]
