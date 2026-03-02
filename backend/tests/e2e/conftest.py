"""
E2E test configuration and fixtures.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="session")
def mock_app_lifespan():
    """Mock the app lifespan to avoid full initialization."""
    with patch("app.main.lifespan") as mock_lifespan:
        # Create a simple async context manager mock
        async def mock_context_manager(app):
            yield

        mock_lifespan.return_value = mock_context_manager
        yield mock_lifespan


@pytest.fixture
def client(mock_app_lifespan):
    """Create a test client for the FastAPI app."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_authentication():
    """Mock authentication dependencies."""
    with patch("app.api.deps.get_current_user") as mock_user:
        mock_user.return_value = MagicMock(
            id="test-user-123",
            member_id="123",
            email="test@example.com",
            is_active=True,
        )
        yield mock_user


@pytest.fixture
def mock_guest_access():
    """Mock guest access verification."""
    with patch("app.api.deps.verify_guest_access") as mock_verify:
        mock_verify.return_value = None
        yield mock_verify


@pytest.fixture
def auth_headers():
    """Return authentication headers for testing."""
    return {"Authorization": "Bearer test-token"}
