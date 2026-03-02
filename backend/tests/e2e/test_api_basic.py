"""
Basic E2E API tests.
Tests API endpoints with mocked dependencies.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_root_endpoint(self, client):
        """Test the root endpoint returns API info."""
        response = client.get("/")
        # Should redirect or return info
        assert response.status_code in [200, 307, 404]

    def test_openapi_endpoint(self, client):
        """Test OpenAPI schema endpoint."""
        response = client.get("/api/v1/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data


class TestSystemEndpoints:
    """Tests for system endpoints."""

    def test_system_info(self, client):
        """Test system info endpoint."""
        with patch("app.api.routes.system.settings") as mock_settings:
            mock_settings.PROJECT_NAME = "TestApp"
            mock_settings.ENVIRONMENT = "testing"

            response = client.get("/api/v1/system/info")
            assert response.status_code == 200
            data = response.json()
            assert "app_name" in data
            assert "version" in data

    def test_system_health(self, client):
        """Test system health endpoint."""
        with patch("app.api.routes.system.engine") as mock_engine:
            # Mock successful health check
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

            response = client.get("/api/v1/system/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data


class TestChatEndpoints:
    """Tests for chat endpoints."""

    def test_chat_endpoint_requires_auth(self, client):
        """Test that chat endpoint requires authentication."""
        response = client.post("/api/v1/chat", json={
            "thread_id": "test-thread",
            "message": "Hello"
        })
        # Should fail without auth or guest_id
        assert response.status_code in [401, 403, 422]

    def test_chat_endpoint_with_mock_auth(self, client, mock_authentication, mock_guest_access):
        """Test chat endpoint with mocked authentication."""
        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            mock_bg.return_value = None

            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.api.routes.agent.session_scope") as mock_session:
                    mock_session.return_value.__aenter__ = AsyncMock(
                        return_value=AsyncMock()
                    )
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": "test-thread",
                        "message": "Hello",
                        "project_id": 1
                    })

                    # Should be accepted
                    assert response.status_code in [200, 202]

    def test_stop_chat_endpoint(self, client, mock_authentication):
        """Test stop chat endpoint."""
        with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
            mock_monitor.stop_run = AsyncMock()

            response = client.post("/api/v1/chat/stop", json={
                "thread_id": "test-thread",
                "message": "stop"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["thread_id"] == "test-thread"
            assert data["status"] == "stopping"


class TestProjectEndpoints:
    """Tests for project endpoints."""

    def test_list_projects(self, client, mock_authentication):
        """Test listing projects."""
        with patch("app.api.routes.projects.project_manager") as mock_pm:
            mock_pm.list_projects = AsyncMock(return_value=[
                {"id": 1, "name": "Project 1", "path": "/path/1"},
                {"id": 2, "name": "Project 2", "path": "/path/2"},
            ])

            response = client.get("/api/v1/projects")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 2

    def test_get_project(self, client, mock_authentication):
        """Test getting a specific project."""
        with patch("app.api.routes.projects.project_manager") as mock_pm:
            mock_pm.get_project = AsyncMock(return_value={
                "id": 1,
                "name": "Test Project",
                "path": "/path/to/project",
            })

            response = client.get("/api/v1/projects/1")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == 1
            assert data["name"] == "Test Project"


class TestMemoryEndpoints:
    """Tests for memory endpoints."""

    def test_search_memory(self, client, mock_authentication):
        """Test memory search endpoint."""
        with patch("app.api.routes.memory.memory_manager") as mock_mm:
            mock_mm.search = AsyncMock(return_value=[
                {"id": "1", "content": "Memory 1", "score": 0.9},
                {"id": "2", "content": "Memory 2", "score": 0.8},
            ])

            response = client.post("/api/v1/memory/search", json={
                "query": "test query",
                "limit": 10
            })

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_add_memory(self, client, mock_authentication):
        """Test adding memory endpoint."""
        with patch("app.api.routes.memory.memory_manager") as mock_mm:
            mock_mm.add = AsyncMock(return_value={"id": "new-memory-id"})

            response = client.post("/api/v1/memory", json={
                "content": "New memory content",
                "tags": ["tag1", "tag2"]
            })

            assert response.status_code in [200, 201]


class TestToolEndpoints:
    """Tests for tool endpoints."""

    def test_list_tools(self, client, mock_authentication):
        """Test listing available tools."""
        with patch("app.api.routes.tools.tool_registry") as mock_registry:
            mock_registry.list_tools = MagicMock(return_value=[
                {"name": "tool1", "description": "Tool 1"},
                {"name": "tool2", "description": "Tool 2"},
            ])

            response = client.get("/api/v1/tools")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_execute_tool(self, client, mock_authentication):
        """Test tool execution endpoint."""
        with patch("app.api.routes.tools.tool_registry") as mock_registry:
            mock_registry.execute = AsyncMock(return_value={
                "success": True,
                "result": "Tool executed successfully"
            })

            response = client.post("/api/v1/tools/execute", json={
                "tool_name": "test_tool",
                "parameters": {"param1": "value1"}
            })

            assert response.status_code == 200


class TestConversationEndpoints:
    """Tests for conversation endpoints."""

    def test_list_conversations(self, client, mock_authentication):
        """Test listing conversations."""
        with patch("app.api.routes.conversations.session_scope") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock()
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get("/api/v1/conversations")
            assert response.status_code == 200

    def test_get_conversation(self, client, mock_authentication):
        """Test getting a specific conversation."""
        with patch("app.api.routes.conversations.session_scope") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock()
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get("/api/v1/conversations/test-thread-id")
            assert response.status_code in [200, 404]


class TestWikiEndpoints:
    """Tests for wiki endpoints."""

    def test_list_wiki_pages(self, client, mock_authentication):
        """Test listing wiki pages."""
        with patch("app.api.routes.wiki.wiki_service") as mock_service:
            mock_service.list_pages = AsyncMock(return_value=[
                {"id": "1", "title": "Page 1"},
                {"id": "2", "title": "Page 2"},
            ])

            response = client.get("/api/v1/wiki/pages")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_get_wiki_page(self, client, mock_authentication):
        """Test getting a wiki page."""
        with patch("app.api.routes.wiki.wiki_service") as mock_service:
            mock_service.get_page = AsyncMock(return_value={
                "id": "1",
                "title": "Test Page",
                "content": "# Test Content"
            })

            response = client.get("/api/v1/wiki/pages/1")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "1"


class TestBrainEndpoints:
    """Tests for brain/cognitive endpoints."""

    def test_brain_status(self, client, mock_authentication):
        """Test brain status endpoint."""
        with patch("app.api.routes.brain.brain_kernel") as mock_brain:
            mock_brain.get_status = AsyncMock(return_value={
                "status": "active",
                "memory_usage": "low",
                "capabilities": ["reasoning", "memory"]
            })

            response = client.get("/api/v1/brain/status")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data

    def test_brain_think(self, client, mock_authentication):
        """Test brain thinking endpoint."""
        with patch("app.api.routes.brain.brain_kernel") as mock_brain:
            mock_brain.think = AsyncMock(return_value={
                "thoughts": ["thought1", "thought2"],
                "conclusion": "Conclusion here"
            })

            response = client.post("/api/v1/brain/think", json={
                "prompt": "Think about this",
                "context": "Some context"
            })

            assert response.status_code == 200
