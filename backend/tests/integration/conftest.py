"""
Pytest configuration for integration tests.
"""

import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test")


def pytest_collection_modifyitems(config, items):
    """Add integration marker to all tests in this directory."""
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def mock_database_session():
    """Globally mock database session_scope for all integration tests."""
    from app.infrastructure.database.resource_manager import db_resource_manager

    # Save and reset db_resource_manager state to prevent pollution from other tests
    original_session_factory = getattr(db_resource_manager, '_session_factory', None)
    original_initialized = getattr(db_resource_manager, '_initialized', False)
    db_resource_manager._initialized = False
    db_resource_manager._session_factory = None

    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=0)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar.return_value = None
    result_mock.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    session.execute.return_value = result_mock

    @asynccontextmanager
    async def _scope():
        # If a real session factory was set by another fixture (e.g. _real_db),
        # delegate to it so tests that need a real DB can function. We must
        # preserve the transactional semantics of the real session_scope (commit
        # on success, rollback on exception), otherwise writes are lost.
        if db_resource_manager._session_factory is not None:
            async with db_resource_manager.session_factory() as real_session:
                try:
                    yield real_session
                    await real_session.commit()
                except (ValueError, OSError, RuntimeError, TypeError, KeyError):
                    await real_session.rollback()
                    raise
                finally:
                    await real_session.close()
        else:
            yield session

    with patch("app.infrastructure.database.session_scope", _scope), \
         patch("app.infrastructure.database.session_scope", _scope), \
         patch("app.core.engine.dispatch.session_scope", _scope), \
         patch("app.core.engine.message.sequence.session_scope", _scope), \
         patch("app.core.engine.message.repository.session_scope", _scope):
        yield session

    # Restore original state
    db_resource_manager._session_factory = original_session_factory
    db_resource_manager._initialized = original_initialized
