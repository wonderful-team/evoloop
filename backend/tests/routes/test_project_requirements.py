"""
Tests for Project Requirements API Routes.

Tests document upload, listing, detail, deletion, and task sync endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from io import BytesIO


class TestUploadRequirementDocument:
    """Tests for document upload endpoint."""

    def test_upload_document_success(self, client, auth_headers, tmp_path):
        """Test successfully uploading a requirement document."""
        with patch("app.api.routes.project_requirements.settings") as mock_settings:
            mock_settings.UPLOAD_DIR = str(tmp_path)

            # Create a proper test file on disk
            test_file = tmp_path / "test_requirements.txt"
            test_file.write_text("Test document content")

            with patch("app.api.routes.project_requirements._save_uploaded_file") as mock_save:
                mock_save.return_value = str(test_file)

                with patch("app.api.routes.project_requirements.document_reader_service") as mock_reader:
                    mock_reader.read_document = AsyncMock(return_value="Test document content")

                    with patch("app.api.routes.project_requirements.run_agent_background") as mock_bg:
                        # Create test file upload
                        file_content = b"Test file content"
                        response = client.post(
                            "/api/v1/projects/1/requirements/upload",
                            headers=auth_headers,
                            files={"file": ("test_requirements.txt", BytesIO(file_content), "text/plain")},
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert "document_id" in data
                        assert "thread_id" in data
                        assert data["status"] == "analysis_started"
                        assert "成功" in data["message"] or "success" in data["message"].lower()

    def test_upload_document_invalid_file_type(self, client, auth_headers, tmp_path):
        """Test uploading a file with unsupported type."""
        with patch("app.api.routes.project_requirements.settings") as mock_settings:
            mock_settings.UPLOAD_DIR = str(tmp_path)

            with patch("app.api.routes.project_requirements._save_uploaded_file") as mock_save:
                test_file = tmp_path / "test.exe"
                test_file.write_bytes(b"Test content")
                mock_save.return_value = str(test_file)

                with patch("app.api.routes.project_requirements.document_reader_service") as mock_reader:
                    mock_reader.read_document = AsyncMock(return_value="Test content")

                    with patch("app.api.routes.project_requirements.run_agent_background"):
                        file_content = b"Test content"
                        response = client.post(
                            "/api/v1/projects/1/requirements/upload",
                            headers=auth_headers,
                            files={"file": ("test.exe", BytesIO(file_content), "application/octet-stream")},
                        )

                        # Should still accept but mark as octet-stream
                        assert response.status_code == 200

    @pytest.mark.skip(reason="Auth handling tested at integration level - complex mocking required")
    def test_upload_document_no_auth(self, client):
        """Test uploading without authentication."""
        # This test verifies the endpoint requires authentication
        # The route uses TokenDep which should reject requests without valid token
        pass


class TestListProjectRequirements:
    """Tests for listing requirement documents."""

    def test_list_requirements_empty(self, client, auth_headers):
        """Test listing requirements with empty result."""
        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result
            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get("/api/v1/projects/1/requirements", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data["items"] == []

    def test_list_requirements_with_docs(self, client, auth_headers):
        """Test listing requirements with documents."""
        mock_doc = MagicMock()
        mock_doc.id = "doc-123"
        mock_doc.file_name = "requirements.docx"
        mock_doc.file_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        mock_doc.status = "analyzed"
        mock_doc.created_at.isoformat = MagicMock(return_value="2024-01-01T00:00:00")
        mock_doc.analyses = [MagicMock(), MagicMock()]

        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_doc]
            mock_session.execute.return_value = mock_result
            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get("/api/v1/projects/1/requirements", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["id"] == "doc-123"
            assert data["items"][0]["file_name"] == "requirements.docx"
            assert data["items"][0]["analysis_count"] == 2


class TestGetRequirementDetail:
    """Tests for getting requirement document detail."""

    def test_get_requirement_detail_success(self, client, auth_headers):
        """Test getting document detail successfully."""
        mock_doc = MagicMock()
        mock_doc.id = "doc-123"
        mock_doc.project_id = 1
        mock_doc.file_name = "requirements.docx"
        mock_doc.file_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        mock_doc.file_size = 1024
        mock_doc.status = "analyzed"
        mock_doc.raw_content = "a" * 2000  # Content longer than preview limit
        mock_doc.created_at.isoformat = MagicMock(return_value="2024-01-01T00:00:00")
        mock_doc.updated_at.isoformat = MagicMock(return_value="2024-01-02T00:00:00")
        mock_doc.analyses = []

        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_doc
            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get("/api/v1/projects/1/requirements/doc-123", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "doc-123"
            assert data["file_name"] == "requirements.docx"
            assert data["raw_content_preview"] == "a" * 1000  # Preview limited to 1000 chars

    def test_get_requirement_detail_not_found(self, client, auth_headers):
        """Test getting non-existent document."""
        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.get.return_value = None
            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get("/api/v1/projects/1/requirements/nonexistent", headers=auth_headers)

            assert response.status_code == 404

    def test_get_requirement_detail_wrong_project(self, client, auth_headers):
        """Test getting document from wrong project."""
        mock_doc = MagicMock()
        mock_doc.project_id = 2  # Different from requested project

        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_doc
            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get("/api/v1/projects/1/requirements/doc-123", headers=auth_headers)

            assert response.status_code == 404


class TestDeleteRequirementDocument:
    """Tests for deleting requirement documents."""

    def test_delete_requirement_success(self, client, auth_headers):
        """Test successfully deleting a document."""
        mock_doc = MagicMock()
        mock_doc.id = "doc-123"
        mock_doc.project_id = 1
        mock_doc.file_path = "/tmp/test.docx"

        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_doc
            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True

                with patch("os.remove") as mock_remove:
                    response = client.delete("/api/v1/projects/1/requirements/doc-123", headers=auth_headers)

                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "deleted"
                    assert data["document_id"] == "doc-123"
                    mock_remove.assert_called_once_with("/tmp/test.docx")

    def test_delete_requirement_not_found(self, client, auth_headers):
        """Test deleting non-existent document."""
        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.get.return_value = None
            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.delete("/api/v1/projects/1/requirements/nonexistent", headers=auth_headers)

            assert response.status_code == 404


class TestGetAnalysisTasks:
    """Tests for getting analysis tasks."""

    def test_get_analysis_tasks_success(self, client, auth_headers):
        """Test getting tasks for an analysis."""
        mock_analysis = MagicMock()
        mock_analysis.project_id = 1

        mock_doc = MagicMock()
        mock_doc.project_id = 1

        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_task.task_data = {
            "title": "Implement login",
            "description": "Create login page",
            "priority": "high",
            "estimated_hours": 4,
            "category": "frontend",
            "tags": ["auth", "ui"],
            "requirement_refs": ["FR-001"],
            "acceptance_criteria": ["User can login"],
        }
        mock_task.sync_status = "synced"
        mock_task.sync_error = None
        mock_task.evocloud_task_id = 456
        mock_task.synced_at.isoformat = MagicMock(return_value="2024-01-01T00:00:00")
        mock_task.created_at.isoformat = MagicMock(return_value="2024-01-01T00:00:00")

        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.get.side_effect = [mock_analysis, mock_doc]

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_task]
            mock_session.execute.return_value = mock_result

            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get(
                "/api/v1/projects/1/requirements/doc-123/analyses/analysis-456/tasks",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["analysis_id"] == "analysis-456"
            assert data["project_id"] == 1
            assert len(data["tasks"]) == 1
            assert data["sync_stats"]["synced"] == 1
            assert data["sync_stats"]["total"] == 1

    def test_get_analysis_tasks_not_found(self, client, auth_headers):
        """Test getting tasks for non-existent analysis."""
        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.get.return_value = None
            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get(
                "/api/v1/projects/1/requirements/doc-123/analyses/nonexistent/tasks",
                headers=auth_headers,
            )

            assert response.status_code == 404


class TestGetAnalysisSyncProgress:
    """Tests for getting sync progress."""

    def test_get_sync_progress_success(self, client, auth_headers):
        """Test getting sync progress successfully."""
        mock_analysis = MagicMock()
        mock_analysis.project_id = 1
        mock_analysis.confirmed_at.isoformat = MagicMock(return_value="2024-01-01T00:00:00")

        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_analysis

            # Mock progress query result
            mock_result = MagicMock()
            mock_result.all.return_value = [
                MagicMock(sync_status="synced", count=5),
                MagicMock(sync_status="pending", count=2),
                MagicMock(sync_status="failed", count=1),
            ]
            mock_session.execute.return_value = mock_result

            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get(
                "/api/v1/projects/1/requirements/doc-123/analyses/analysis-456/sync-progress",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["analysis_id"] == "analysis-456"
            assert data["progress"]["total"] == 8
            assert data["progress"]["synced"] == 5
            assert data["progress"]["pending"] == 2
            assert data["progress"]["failed"] == 1
            assert data["progress"]["percentage"] == 62.5
            assert data["progress"]["is_complete"] is False
            assert data["progress"]["has_failures"] is True

    def test_get_sync_progress_complete(self, client, auth_headers):
        """Test getting sync progress when all tasks are synced."""
        mock_analysis = MagicMock()
        mock_analysis.project_id = 1
        mock_analysis.confirmed_at.isoformat = MagicMock(return_value="2024-01-01T00:00:00")

        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_analysis

            mock_result = MagicMock()
            mock_result.all.return_value = [
                MagicMock(sync_status="synced", count=10),
            ]
            mock_session.execute.return_value = mock_result

            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get(
                "/api/v1/projects/1/requirements/doc-123/analyses/analysis-456/sync-progress",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["progress"]["total"] == 10
            assert data["progress"]["synced"] == 10
            assert data["progress"]["percentage"] == 100.0
            assert data["progress"]["is_complete"] is True
            assert data["progress"]["has_failures"] is False

    def test_get_sync_progress_not_found(self, client, auth_headers):
        """Test getting progress for non-existent analysis."""
        with patch("app.api.routes.project_requirements.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.get.return_value = None
            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get(
                "/api/v1/projects/1/requirements/doc-123/analyses/nonexistent/sync-progress",
                headers=auth_headers,
            )

            assert response.status_code == 404
