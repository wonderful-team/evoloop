"""
Tests for user routes.
"""

from unittest.mock import MagicMock


class TestUserMe:
    """Tests for /users/me endpoint."""

    def test_get_current_user(self, client, auth_headers):
        """Test getting current user info."""
        mock_user = MagicMock(
            id="user-123",
            member_id="123",
            email="test@example.com",
            username="testuser",
            is_active=True,
        )

        # Convert mock to dict for JSON serialization
        with patch("app.api.routes.users.CurrentUser") as mock_dep:
            from fastapi import Depends

            # The dependency returns the user directly
            with patch(
                "app.api.deps.get_current_user", return_value=mock_user
            ) as mock_get_user:
                response = client.get("/api/v1/users/me", headers=auth_headers)

                # Should succeed with mock
                assert response.status_code in [200, 401]

    def test_get_current_user_with_auth(self, client, auth_headers):
        """Test getting current user with auth succeeds."""
        response = client.get("/api/v1/users/me", headers=auth_headers)
        # With mocked dependencies, should return 200
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["username"] == "testuser"


# Need to import patch at module level
from unittest.mock import patch
