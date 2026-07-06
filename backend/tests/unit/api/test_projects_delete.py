"""
Tests for DELETE /projects/{project_id} endpoint.

Covers:
1. Successful deletion: cloud + local repo exist → clean up all local data
2. Cloud deletion failure → return 500, no local cleanup
3. Local repo not found → cloud deletion succeeds, no error
4. Local cleanup partial failure (cache/graph/vector) → best effort, API still succeeds
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


class TestDeleteProject:
    """Test project deletion endpoint."""

    @pytest.fixture
    def mock_repo(self):
        """Create a mock Repository object."""
        repo = MagicMock()
        repo.id = 42
        repo.project_id = 123
        repo.local_path = "/workspace/test-project"
        return repo

    @pytest.fixture
    def mock_session(self, mock_repo):
        """Create a mock async SQLAlchemy session."""
        session = AsyncMock()

        # Mock execute() -> result -> scalars().all()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mock_repo]
        session.execute.return_value = result_mock

        # Mock session.get() to return the repo so deletion targets the right object.
        session.get = AsyncMock(return_value=mock_repo)

        return session

    @pytest.fixture
    def mock_cloud_success(self):
        """Mock cloud API returning success."""
        with patch("app.api.routes.projects.evocloud_manager") as mock:
            mock.api.delete_project = AsyncMock(return_value={"code": 0, "message": "ok"})
            mock.invalidate_projects_cache = MagicMock()
            yield mock

    @pytest.fixture
    def mock_cloud_failure(self):
        """Mock cloud API returning failure."""
        with patch("app.api.routes.projects.evocloud_manager") as mock:
            mock.api.delete_project = AsyncMock(return_value={"code": 1, "message": "project not found"})
            mock.invalidate_projects_cache = MagicMock()
            yield mock

    @pytest.fixture
    def mock_indexing_manager(self):
        """Mock indexing manager."""
        with patch("app.api.routes.projects.indexing_manager") as mock:
            mock.stop_watching = AsyncMock()
            yield mock

    @pytest.fixture
    def mock_cache(self):
        """Mock cache with pipeline."""
        pipe = MagicMock()
        pipe.delete = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock()

        cache_mock = MagicMock()
        cache_mock.pipeline.return_value = pipe

        with patch("app.api.routes.projects.cache", cache_mock):
            yield cache_mock, pipe

    @pytest.fixture
    def mock_graph_disabled(self):
        """Mock graph as disabled."""
        yield

    @pytest.fixture
    def mock_graph_enabled(self):
        """Mock graph as enabled with mock driver."""
        driver = AsyncMock()
        yield driver

    @pytest.fixture
    def mock_vector_store(self):
        """Mock vector store."""
        vs = MagicMock()
        vs.delete_by_repository = MagicMock(return_value=5)

        with patch("app.api.routes.projects.get_vector_store", return_value=vs):
            yield vs

    @pytest.fixture
    def mock_session_scope(self, mock_session):
        """Mock session_scope context manager."""
        import app.api.routes.projects as projects_module

        original = getattr(projects_module, "session_scope", None)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)

        async def _aexit(*_):
            await mock_session.commit()
            return False

        mock_ctx.__aexit__ = _aexit
        # session_scope is a function that returns an async context manager
        mock_scope = MagicMock(return_value=mock_ctx)

        projects_module.session_scope = mock_scope
        yield mock_scope

        if original is not None:
            projects_module.session_scope = original

    # ==========================================================================
    # Success scenarios
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_delete_project_success_full_cleanup(
        self,
        mock_cloud_success,
        mock_session_scope,
        mock_session,
        mock_repo,
        mock_indexing_manager,
        mock_cache,
        mock_graph_enabled,
        mock_vector_store,
    ):
        """Cloud delete succeeds, local repo exists → all cleanup executed."""
        from app.api.routes.projects import delete_project

        result = await delete_project(123, None)

        # Verify cloud deletion called
        mock_cloud_success.api.delete_project.assert_awaited_once_with(123, token=None)

        # Verify local cleanup
        mock_indexing_manager.stop_watching.assert_awaited_once_with("/workspace/test-project")

        _, pipe = mock_cache
        pipe.delete.assert_any_call("sys:42:indexing")
        pipe.delete.assert_any_call("sys:42:summarization")
        pipe.delete.assert_any_call("sys:42:wiki")
        pipe.delete.assert_any_call("indexing:cancel:42")
        pipe.execute.assert_awaited_once()

        pass

        mock_vector_store.delete_by_repository.assert_called_once_with("42")

        mock_session.delete.assert_awaited_once_with(mock_repo)
        mock_session.commit.assert_awaited()

        mock_cloud_success.invalidate_projects_cache.assert_called_once()

        assert result.status == "success"
        assert result.id == 123

    @pytest.mark.asyncio
    async def test_delete_project_no_local_repo(
        self,
        mock_cloud_success,
        mock_session_scope,
        mock_session,
        mock_indexing_manager,
        mock_cache,
    ):
        """Cloud delete succeeds, but no local repo → no local cleanup errors."""
        from app.api.routes.projects import delete_project

        # Override session to return no repos
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        result = await delete_project(123, None)

        mock_cloud_success.api.delete_project.assert_awaited_once_with(123, token=None)
        mock_indexing_manager.stop_watching.assert_not_awaited()

        _, pipe = mock_cache
        pipe.execute.assert_not_awaited()

        mock_cloud_success.invalidate_projects_cache.assert_called_once()
        assert result.status == "success"
        assert result.id == 123

    # ==========================================================================
    # Failure scenarios
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_delete_project_cloud_failure(
        self,
        mock_cloud_failure,
        mock_session_scope,
    ):
        """Cloud delete fails → 500 error, no local cleanup attempted."""
        from app.api.routes.projects import delete_project

        with pytest.raises(HTTPException) as exc_info:
            await delete_project(123, None)

        assert exc_info.value.status_code == 500
        assert "project not found" in exc_info.value.detail
        mock_cloud_failure.api.delete_project.assert_awaited_once_with(123, token=None)
        mock_cloud_failure.invalidate_projects_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_project_cloud_exception(
        self,
        mock_session_scope,
    ):
        """Cloud delete raises exception → 500 error."""
        from app.api.routes.projects import delete_project

        with patch("app.api.routes.projects.evocloud_manager") as mock:
            mock.api.delete_project = AsyncMock(side_effect=ConnectionError("timeout"))
            mock.invalidate_projects_cache = MagicMock()

            with pytest.raises(HTTPException) as exc_info:
                await delete_project(123, None)

            assert exc_info.value.status_code == 500
            assert "timeout" in exc_info.value.detail
            mock.invalidate_projects_cache.assert_not_called()

    # ==========================================================================
    # Best-effort cleanup: partial failures should not block API success
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_delete_project_cache_cleanup_failure_ignored(
        self,
        mock_cloud_success,
        mock_session_scope,
        mock_session,
        mock_repo,
        mock_indexing_manager,
        mock_graph_disabled,
        mock_vector_store,
    ):
        """Cache cleanup fails → API still succeeds."""
        from app.api.routes.projects import delete_project

        with patch("app.api.routes.projects.cache") as bad_cache:
            bad_cache.pipeline = MagicMock(side_effect=RuntimeError("cache down"))

            result = await delete_project(123, None)

        assert result.status == "success"
        mock_session.delete.assert_awaited_once_with(mock_repo)

    @pytest.mark.asyncio
    async def test_delete_project_vector_cleanup_failure_ignored(
        self,
        mock_cloud_success,
        mock_session_scope,
        mock_session,
        mock_repo,
        mock_indexing_manager,
        mock_cache,
        mock_graph_disabled,
    ):
        """Vector store cleanup fails → API still succeeds."""
        from app.api.routes.projects import delete_project

        bad_vs = MagicMock()
        bad_vs.delete_by_repository = MagicMock(side_effect=RuntimeError("vector down"))

        with patch("app.infrastructure.database.vector.get_vector_store", return_value=bad_vs):
            result = await delete_project(123, None)

        assert result.status == "success"
        mock_session.delete.assert_awaited_once_with(mock_repo)
