"""
Tests for brain routes.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestBrainChat:
    """Tests for brain chat endpoint."""

    def test_brain_chat_success(self, client, auth_headers):
        """Test successful brain chat request."""
        with patch("app.api.routes.brain.get_kernel") as mock_get_kernel:
            mock_kernel = MagicMock()
            mock_kernel.step = AsyncMock(return_value="This is the brain's response")
            mock_get_kernel.return_value = mock_kernel

            response = client.post(
                "/api/v1/brain/chat",
                headers=auth_headers,
                json={
                    "query": "Analyze this problem",
                    "max_depth": 3,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "response" in data
            assert data["response"] == "This is the brain's response"
            assert data["mode"] == "fast"

    def test_brain_chat_default_max_depth(self, client, auth_headers):
        """Test brain chat with default max_depth."""
        with patch("app.api.routes.brain.get_kernel") as mock_get_kernel:
            mock_kernel = MagicMock()
            mock_kernel.step = AsyncMock(return_value="Response with default depth")
            mock_get_kernel.return_value = mock_kernel

            response = client.post(
                "/api/v1/brain/chat",
                headers=auth_headers,
                json={"query": "Simple question"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["response"] == "Response with default depth"

    def test_brain_chat_kernel_error(self, client, auth_headers):
        """Test brain chat when kernel raises an error."""
        with patch("app.api.routes.brain.get_kernel") as mock_get_kernel:
            mock_kernel = MagicMock()
            mock_kernel.step = AsyncMock(side_effect=Exception("Kernel failure"))
            mock_get_kernel.return_value = mock_kernel

            response = client.post(
                "/api/v1/brain/chat",
                headers=auth_headers,
                json={"query": "This will fail"},
            )
            assert response.status_code == 500
            data = response.json()
            assert "detail" in data

    def test_brain_chat_kernel_initialization(self, client, auth_headers):
        """Test that kernel is lazily initialized."""
        with patch("app.api.routes.brain._kernel_instance", None):
            with patch("app.api.routes.brain.LightningKernel") as mock_kernel_class:
                mock_kernel = MagicMock()
                mock_kernel.initialize = AsyncMock()
                mock_kernel.step = AsyncMock(return_value="Initialized response")
                mock_kernel_class.return_value = mock_kernel

                response = client.post(
                    "/api/v1/brain/chat",
                    headers=auth_headers,
                    json={"query": "First query"},
                )
                assert response.status_code == 200
                mock_kernel.initialize.assert_called_once()

    def test_brain_chat_kernel_reuse(self, client, auth_headers):
        """Test that kernel instance is reused after initialization."""
        mock_kernel = MagicMock()
        mock_kernel.step = AsyncMock(return_value="Reused response")

        with patch("app.api.routes.brain._kernel_instance", mock_kernel):
            response = client.post(
                "/api/v1/brain/chat",
                headers=auth_headers,
                json={"query": "Second query"},
            )
            assert response.status_code == 200
            # Initialize should not be called again
            mock_kernel.initialize.assert_not_called()

    def test_brain_chat_validation_error(self, client):
        """Test brain chat with invalid request data."""
        response = client.post(
            "/api/v1/brain/chat",
            json={"invalid_field": "missing query"},
        )
        # Should fail validation
        assert response.status_code == 422
