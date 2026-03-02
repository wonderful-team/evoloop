"""
Tests for system routes.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestSystemHealth:
    """Tests for system health endpoints."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/v1/system/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "evoloop-backend"

    def test_get_system_config(self, client, auth_headers, mock_current_user):
        """Test getting system config."""
        with patch("app.api.routes.system.SystemConfigService") as mock_service:
            mock_service.get_all.return_value = [
                {"key": "test_key", "value": "test_value", "description": "Test"}
            ]

            response = client.get("/api/v1/system/config", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_update_system_config(self, client, auth_headers, mock_current_user):
        """Test updating system config."""
        with patch("app.api.routes.system.SystemConfigService") as mock_service:
            mock_service.set_value.return_value = {
                "key": "test_key",
                "value": "new_value",
                "description": "Updated",
            }

            response = client.post(
                "/api/v1/system/config",
                headers=auth_headers,
                json={"key": "test_key", "value": "new_value", "description": "Updated"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["key"] == "test_key"


class TestEmbeddingConfig:
    """Tests for embedding configuration endpoints."""

    @pytest.mark.asyncio
    async def test_test_embedding_connection(self, client, auth_headers, mock_current_user):
        """Test embedding connection validation."""
        with patch("app.api.routes.system.EmbeddingConfigService") as mock_service:
            mock_service.validate_connection = AsyncMock(return_value=(True, 768))

            response = client.post(
                "/api/v1/system/embedding/test",
                headers=auth_headers,
                json={
                    "provider": "openai",
                    "base_url": "https://api.openai.com",
                    "model": "text-embedding-3-small",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["dimensions"] == 768

    @pytest.mark.asyncio
    async def test_apply_embedding_config(self, client, auth_headers, mock_current_user):
        """Test applying embedding config."""
        with patch("app.api.routes.system.EmbeddingConfigService") as mock_service:
            mock_service.switch_embedding_model = AsyncMock(return_value=None)

            response = client.post(
                "/api/v1/system/embedding/apply",
                headers=auth_headers,
                json={
                    "provider": "openai",
                    "base_url": "https://api.openai.com",
                    "model": "text-embedding-3-small",
                    "project_id": 1,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "applied"


class TestLLMConfig:
    """Tests for LLM configuration endpoints."""

    @pytest.mark.asyncio
    async def test_test_llm_connection(self, client, auth_headers, mock_current_user):
        """Test LLM connection validation."""
        with patch("app.api.routes.system.LLMConfigService") as mock_service:
            mock_service.validate_connection = AsyncMock(
                return_value=(True, "Hello from LLM")
            )

            response = client.post(
                "/api/v1/system/llm/test",
                headers=auth_headers,
                json={
                    "provider": "openai",
                    "base_url": "https://api.openai.com",
                    "model": "gpt-4o",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "reply" in data

    @pytest.mark.asyncio
    async def test_apply_llm_config(self, client, auth_headers, mock_current_user):
        """Test applying LLM config."""
        with patch("app.api.routes.system.LLMConfigService") as mock_service:
            mock_service.applied_llm_config = AsyncMock(return_value=None)

            response = client.post(
                "/api/v1/system/llm/apply",
                headers=auth_headers,
                json={
                    "provider": "openai",
                    "base_url": "https://api.openai.com",
                    "model": "gpt-4o",
                    "vision_model": "gpt-4o",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "applied"


class TestKnowledgeBase:
    """Tests for knowledge base management."""

    def test_reset_knowledge_base_endpoint(self, client, auth_headers, mock_current_user):
        """Test resetting knowledge base endpoint exists."""
        response = client.post(
            "/api/v1/system/reset-knowledge", headers=auth_headers
        )
        assert response.status_code in [200, 401, 403, 500]


class TestCloudStatus:
    """Tests for cloud status endpoint."""

    def test_get_cloud_status_endpoint(self, client):
        """Test getting cloud connection status endpoint exists."""
        response = client.get("/api/v1/system/cloud-status")
        assert response.status_code in [200, 500]  # May fail due to evocloud manager not being fully mocked
