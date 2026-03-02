"""
Shared fixtures for route tests.
"""

import sys
from unittest.mock import patch, MagicMock, AsyncMock, Mock

# ===== Module-level patches (must happen before any app imports) =====

# Patch Neo4j module before any app imports
mock_neo4j_module = MagicMock()
mock_neo4j_driver = MagicMock()
mock_neo4j_driver.verify_connectivity = AsyncMock()
mock_neo4j_driver.close = AsyncMock()
mock_neo4j_driver.execute_query = AsyncMock(return_value=([], None, None))
mock_neo4j_module.AsyncGraphDatabase.driver = MagicMock(return_value=mock_neo4j_driver)
sys.modules['neo4j'] = mock_neo4j_module

# Patch Redis - Create comprehensive mock with all required async methods
mock_redis_client = MagicMock()

# Basic key operations
mock_redis_client.get = AsyncMock(return_value=None)
mock_redis_client.set = AsyncMock()
mock_redis_client.delete = AsyncMock()
mock_redis_client.exists = AsyncMock(return_value=0)
mock_redis_client.incr = AsyncMock(return_value=1)
mock_redis_client.expire = AsyncMock()

# Hash operations (for activity monitor)
mock_redis_client.hset = AsyncMock()
mock_redis_client.hget = AsyncMock(return_value=None)
mock_redis_client.hgetall = AsyncMock(return_value={})
mock_redis_client.hdel = AsyncMock()

# List operations
mock_redis_client.lpush = AsyncMock()
mock_redis_client.ltrim = AsyncMock()

# Pub/Sub operations
mock_redis_client.publish = AsyncMock()

# Lock operations
mock_lock_context = AsyncMock()
mock_lock_context.__aenter__ = AsyncMock(return_value=True)
mock_lock_context.__aexit__ = AsyncMock(return_value=False)
mock_redis_client.lock = MagicMock(return_value=mock_lock_context)

# Pipeline
mock_redis_client.pipeline = MagicMock(return_value=MagicMock(
    get=MagicMock(return_value=MagicMock()),
    set=MagicMock(return_value=MagicMock()),
    delete=MagicMock(return_value=MagicMock()),
    hget=MagicMock(return_value=MagicMock()),
    execute=AsyncMock(return_value=[None, None, None])
))

import pytest
import pytest_asyncio


# Patch before any imports
@pytest.fixture(scope="session", autouse=True)
def patch_global_dependencies():
    """Patch global dependencies before any app imports."""
    patches = []

    # Patch engine creation
    mock_engine = MagicMock()
    engine_patch = patch("app.infrastructure.database.sql.database.create_async_engine", return_value=mock_engine)
    engine_patch.start()
    patches.append(engine_patch)

    # Patch Redis at the module level
    redis_patch = patch("app.infrastructure.database.redis.redis_client", mock_redis_client)
    redis_patch.start()
    patches.append(redis_patch)

    # Patch lifespan to avoid full initialization
    async def mock_lifespan_context(app):
        yield

    lifespan_patch = patch("app.main.lifespan", mock_lifespan_context)
    lifespan_patch.start()
    patches.append(lifespan_patch)

    yield

    # Stop all patches
    for p in patches:
        p.stop()


@pytest.fixture
def mock_db_session():
    """Create a mock database session for all tests."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.scalars = AsyncMock()
    mock_session.scalar = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.delete = MagicMock()

    # Mock query builder pattern for execute()
    mock_result = MagicMock()
    mock_result.all = AsyncMock(return_value=[])
    mock_result.first = AsyncMock(return_value=None)
    mock_result.scalar = AsyncMock(return_value=None)
    mock_result.scalar_one_or_none = AsyncMock(return_value=None)
    mock_result.scalars = MagicMock(return_value=AsyncMock(all=AsyncMock(return_value=[])))
    mock_session.execute.return_value = mock_result

    # Mock scalars() method
    mock_scalars_result = MagicMock()
    mock_scalars_result.first = MagicMock(return_value=None)
    mock_scalars_result.all = MagicMock(return_value=[])
    mock_scalars_result.one_or_none = MagicMock(return_value=None)
    mock_session.scalars.return_value = mock_scalars_result

    return mock_session


@pytest.fixture
def client(mock_db_session, mock_current_user):
    """Create test client with mocked dependencies."""
    from fastapi.testclient import TestClient
    from app.api import deps

    # Patch session_scope
    with patch("app.infrastructure.database.sql.database.session_scope") as mock_session_scope:
        mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

        # Import app after all patches are in place
        from app.main import app

        # Override dependencies for testing
        app.dependency_overrides[deps.get_current_user] = lambda: mock_current_user
        app.dependency_overrides[deps.verify_guest_access] = lambda: None

        # Override OAuth2 scheme to bypass token validation
        async def mock_oauth2_scheme():
            return "mock-token"

        app.dependency_overrides[deps.oauth2_scheme] = mock_oauth2_scheme
        app.dependency_overrides[deps.oauth2_scheme_optional] = mock_oauth2_scheme

        with TestClient(app) as test_client:
            yield test_client

        # Clean up overrides
        app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    """Return authentication headers."""
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def mock_current_user():
    """Mock current user dependency."""
    from app.models import User

    return User(
        id=1,
        member_id=123,
        email="test@example.com",
        username="testuser",
        is_active=True,
    )


@pytest.fixture
def mock_guest_access():
    """Mock guest access verification."""
    with patch("app.api.deps.verify_guest_access", return_value=None):
        yield


@pytest.fixture
def mock_no_auth():
    """Mock endpoints to not require auth (for testing public endpoints)."""
    with patch("app.api.deps.get_current_user", return_value=None):
        with patch("app.api.deps.verify_guest_access", return_value=None):
            yield
