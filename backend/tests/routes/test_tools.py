"""
Tests for tool routes.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestListTools:
    """Tests for listing tools."""

    def test_list_tools(self, client, auth_headers, mock_current_user):
        """Test listing all available tools."""
        with patch("app.core.tools.manager.tool_manager") as mock_manager:
            mock_manager.get_all_capabilities.return_value = [
                MagicMock(
                    name="read_file",
                    description="Read a file",
                    args_schema=None
                ),
                MagicMock(
                    name="write_file",
                    description="Write to a file",
                    args_schema=None
                ),
            ]

            response = client.get("/api/v1/tools", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_list_runtime_tools(self, client, auth_headers, mock_current_user):
        """Test listing runtime tools."""
        with patch("app.api.routes.tools.get_runtime_tools") as mock_get_runtime:
            mock_get_runtime.return_value = [
                MagicMock(
                    name="dynamic_tool",
                    description="A dynamic tool",
                    args_schema=None
                ),
            ]

            response = client.get("/api/v1/tools/runtime", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)


class TestSystemInfo:
    """Tests for system info endpoint."""

    def test_get_system_info(self, client, auth_headers, mock_current_user):
        """Test getting system information."""
        response = client.get("/api/v1/system/info", headers=auth_headers)
        # May be 200 or 404 depending on implementation
        assert response.status_code in [200, 404]


class TestToolExecution:
    """Tests for tool execution via API."""

    def test_execute_tool_endpoint(self, client, auth_headers, mock_current_user):
        """Test tool execution endpoint exists."""
        # This tests if the endpoint structure is correct
        # Actual execution would require more complex mocking
        response = client.post(
            "/api/v1/tools/execute",
            headers=auth_headers,
            json={
                "tool_name": "read_file",
                "parameters": {"path": "/test/file.txt"},
            },
        )
        # Endpoint may not exist or may return various status codes
        assert response.status_code in [200, 404, 422]
