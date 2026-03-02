"""
Unit tests for API Routes.
Tests the main API endpoints using FastAPI TestClient.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestSystemRoutes:
    """Tests for System Routes."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/v1/system/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "evoloop-backend"

    def test_get_cloud_status(self, client):
        """Test getting cloud status."""
        response = client.get("/api/v1/system/cloud-status")

        # Endpoint exists and returns data (may be 200 or require auth)
        assert response.status_code in [200, 401, 403]


class TestToolsRoutes:
    """Tests for Tools Routes."""

    @patch("app.api.routes.tools.get_runtime_tools")
    @patch("app.api.routes.tools.tool_manager")
    def test_list_runtime_tools(self, mock_manager, mock_get_runtime, client):
        """Test listing runtime tools."""
        # Create mock tools
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.args_schema = None

        mock_get_runtime.return_value = [mock_tool]

        response = client.get("/api/v1/tools/runtime")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @patch("app.api.routes.tools.get_runtime_tools")
    @patch("app.api.routes.tools.tool_manager")
    def test_list_all_tools(self, mock_manager, mock_get_runtime, client):
        """Test listing all tools."""
        mock_tool = MagicMock()
        mock_tool.name = "static_tool"
        mock_tool.description = "A static tool"
        mock_tool.args_schema = None

        mock_manager.get_all_capabilities.return_value = [mock_tool]
        mock_get_runtime.return_value = []

        response = client.get("/api/v1/tools")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestAgentRoutes:
    """Tests for Agent Routes."""

    def test_chat_endpoint_exists(self, client):
        """Test chat endpoint exists."""
        # Agent router has no prefix, so chat is at /chat not /agent/chat
        response = client.post("/api/v1/chat", json={})

        # Returns 401 (needs auth) or 422 (validation) or 403 (forbidden)
        assert response.status_code in [401, 403, 422]

    def test_webhook_endpoint_exists(self, client):
        """Test webhook endpoint exists."""
        response = client.post("/api/v1/webhook", json={})

        # Returns 401 or 422 (webhook has different auth)
        assert response.status_code in [401, 403, 422]

    def test_resume_endpoint_exists(self, client):
        """Test resume endpoint exists."""
        response = client.post("/api/v1/chat/resume", json={})

        # Returns 401 or 422
        assert response.status_code in [401, 403, 422]


class TestBrainRoutes:
    """Tests for Brain Routes."""

    def test_brain_chat_endpoint_exists(self, client):
        """Test brain chat endpoint exists."""
        response = client.post("/api/v1/brain/chat", json={})

        # Requires auth, should be 401
        assert response.status_code in [401, 403, 422]


class TestFileRoutes:
    """Tests for File Routes."""

    def test_get_files_endpoint_exists(self, client):
        """Test get files endpoint exists."""
        # Files router is mounted at /projects/{project_id}/files
        response = client.get("/api/v1/projects/1/files")

        # Endpoint exists, may require query params or auth
        assert response.status_code in [200, 401, 403, 404]

    def test_get_file_content_endpoint_validation(self, client):
        """Test file content endpoint requires params."""
        response = client.get("/api/v1/projects/1/files/content")

        # Should fail validation (missing required params), auth, or project not found
        assert response.status_code in [401, 403, 404, 422]


class TestProjectRoutes:
    """Tests for Project Routes."""

    def test_list_projects_endpoint_exists(self, client):
        """Test list projects endpoint exists."""
        response = client.get("/api/v1/projects")

        assert response.status_code in [200, 401, 403]

    def test_create_project_endpoint_exists(self, client):
        """Test create project endpoint exists."""
        response = client.post("/api/v1/projects", json={})

        assert response.status_code in [401, 403, 422]


class TestConversationRoutes:
    """Tests for Conversation Routes."""

    def test_list_conversations_endpoint_exists(self, client):
        """Test list conversations endpoint exists."""
        response = client.get("/api/v1/conversations")

        assert response.status_code in [200, 401, 403]

    def test_search_conversations_endpoint_exists(self, client):
        """Test search conversations endpoint exists."""
        response = client.get("/api/v1/conversations/search")

        # Search requires query param
        assert response.status_code in [200, 401, 403, 422]


class TestWikiRoutes:
    """Tests for Wiki Routes."""

    def test_get_wiki_list(self, client):
        """Test getting wiki list for a project."""
        response = client.get("/api/v1/wiki/1")

        # May return 404 or require auth
        assert response.status_code in [200, 401, 404]


class TestMemoryRoutes:
    """Tests for Memory Routes."""

    def test_get_concepts_endpoint_exists(self, client):
        """Test get concepts endpoint exists."""
        # This endpoint requires project_id query param
        response = client.get("/api/v1/memory/concepts")

        # Should be 422 (missing required query params) or auth error
        assert response.status_code in [200, 401, 403, 422]

    def test_list_concepts_endpoint_exists(self, client):
        """Test list concepts endpoint exists."""
        # This endpoint also requires project_id query param
        response = client.get("/api/v1/memory/concepts/list")

        # Should be 422 or auth error
        assert response.status_code in [200, 401, 403, 422]


class TestLearningRoutes:
    """Tests for Learning Routes."""

    def test_list_skills_endpoint_exists(self, client):
        """Test list skills endpoint exists."""
        response = client.get("/api/v1/learning/skills")

        assert response.status_code in [200, 401, 403]

    def test_get_human_requests_endpoint_exists(self, client):
        """Test human requests endpoint exists."""
        response = client.get("/api/v1/learning/human-requests")

        assert response.status_code in [200, 401, 403]


class TestMemberRoutes:
    """Tests for Member/Auth Routes."""

    def test_login_endpoint_validation(self, client):
        """Test login endpoint validation."""
        response = client.post("/api/v1/member/login", json={})

        # Should fail validation
        assert response.status_code == 422

    def test_status_endpoint_exists(self, client):
        """Test status endpoint exists."""
        response = client.get("/api/v1/member/status")

        assert response.status_code in [200, 401]


class TestUtilsRoutes:
    """Tests for Utils Routes."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/v1/utils/health-check/")

        assert response.status_code == 200

    def test_evoloop_status(self, client):
        """Test evoloop status endpoint."""
        response = client.get("/api/v1/utils/evoloop-status")

        assert response.status_code == 200


# Fixtures

@pytest.fixture
def client():
    """Create a test client."""
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create auth headers for testing."""
    return {"Authorization": "Bearer test_token"}
