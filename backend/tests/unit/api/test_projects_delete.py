"""
Tests for DELETE /projects/{project_id} endpoint.

Covers:
1. Successful deletion: cloud + local repo exist → clean up all local data
2. Cloud deletion failure → return 500, no local cleanup
3. Local repo not found → cloud deletion succeeds, no error
4. Local cleanup partial failure (cache/graph/vector) → best effort, API still succeeds
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
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

        # Mock execute() -> result -> scalars().first()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = mock_repo
        session.execute.return_value = result_mock

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

        with patch("app.infrastructure.cache.cache", cache_mock):
            yield cache_mock, pipe

    @pytest.fixture
    def mock_graph_disabled(self):
        """Mock graph as disabled."""
        with patch("app.infrastructure.database.graph.driver.is_graph_enabled", return_value=False):
            yield

    @pytest.fixture
    def mock_graph_enabled(self):
        """Mock graph as enabled with mock driver."""
        graph_session = AsyncMock()
        driver = MagicMock()
        driver.session.return_value.__aenter__ = AsyncMock(return_value=graph_session)
        driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.infrastructure.database.graph.driver.is_graph_enabled", return_value=True), \
             patch("app.infrastructure.database.graph.driver.get_graph_db", AsyncMock(return_value=driver)):
            yield driver, graph_session

    @pytest.fixture
    def mock_vector_store(self):
        """Mock vector store."""
        vs = MagicMock()
        vs.delete_by_repository = MagicMock(return_value=5)

        with patch("app.infrastructure.database.vector.get_vector_store", return_value=vs):
            yield vs

    @pytest.fixture
    def mock_async_session_local(self, mock_session):
        """Mock AsyncSessionLocal context manager."""
        import app.api.routes.projects as projects_module

        original = getattr(projects_module, "AsyncSessionLocal", None)
        mock_cls = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        projects_module.AsyncSessionLocal = mock_cls
        yield mock_cls

        if original is not None:
            projects_module.AsyncSessionLocal = original

    # ==========================================================================
    # Success scenarios
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_delete_project_success_full_cleanup(
        self,
        mock_cloud_success,
        mock_async_session_local,
        mock_session,
        mock_repo,
        mock_indexing_manager,
        mock_cache,
        mock_graph_enabled,
        mock_vector_store,
    ):
        """Cloud delete succeeds, local repo exists → all cleanup executed."""
        from app.api.routes.projects import delete_project

        result = await delete_project(123)

        # Verify cloud deletion called
        mock_cloud_success.api.delete_project.assert_awaited_once_with(123)

        # Verify local cleanup
        mock_indexing_manager.stop_watching.assert_awaited_once_with("/workspace/test-project")

        _, pipe = mock_cache
        pipe.delete.assert_any_call("sys:123:indexing")
        pipe.delete.assert_any_call("sys:123:summarization")
        pipe.delete.assert_any_call("sys:123:wiki")
        pipe.execute.assert_awaited_once()

        driver, graph_session = mock_graph_enabled
        graph_session.run.assert_awaited_once()
        call_args = graph_session.run.call_args
        assert "DETACH DELETE" in call_args[0][0]
        assert call_args[1]["pid"] == 123

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
        mock_async_session_local,
        mock_session,
        mock_indexing_manager,
        mock_cache,
    ):
        """Cloud delete succeeds, but no local repo → no local cleanup errors."""
        from app.api.routes.projects import delete_project

        # Override session to return no repo
        mock_session.execute.return_value.scalars.return_value.first.return_value = None

        result = await delete_project(123)

        mock_cloud_success.api.delete_project.assert_awaited_once_with(123)
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
        mock_async_session_local,
    ):
        """Cloud delete fails → 500 error, no local cleanup attempted."""
        from app.api.routes.projects import delete_project

        with pytest.raises(HTTPException) as exc_info:
            await delete_project(123)

        assert exc_info.value.status_code == 500
        assert "project not found" in exc_info.value.detail
        mock_cloud_failure.api.delete_project.assert_awaited_once_with(123)
        mock_cloud_failure.invalidate_projects_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_project_cloud_exception(
        self,
        mock_async_session_local,
    ):
        """Cloud delete raises exception → 500 error."""
        from app.api.routes.projects import delete_project

        with patch("app.api.routes.projects.evocloud_manager") as mock:
            mock.api.delete_project = AsyncMock(side_effect=ConnectionError("timeout"))
            mock.invalidate_projects_cache = MagicMock()

            with pytest.raises(HTTPException) as exc_info:
                await delete_project(123)

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
        mock_async_session_local,
        mock_session,
        mock_repo,
        mock_indexing_manager,
        mock_graph_disabled,
        mock_vector_store,
    ):
        """Cache cleanup fails → API still succeeds."""
        from app.api.routes.projects import delete_project

        with patch("app.infrastructure.cache.cache") as bad_cache:
            bad_cache.pipeline = MagicMock(side_effect=RuntimeError("cache down"))

            result = await delete_project(123)

        assert result.status == "success"
        mock_session.delete.assert_awaited_once_with(mock_repo)

    @pytest.mark.asyncio
    async def test_delete_project_graph_cleanup_failure_ignored(
        self,
        mock_cloud_success,
        mock_async_session_local,
        mock_session,
        mock_repo,
        mock_indexing_manager,
        mock_cache,
        mock_vector_store,
    ):
        """Graph cleanup fails → API still succeeds."""
        from app.api.routes.projects import delete_project

        bad_driver = MagicMock()
        bad_driver.session = MagicMock(side_effect=RuntimeError("graph down"))

        with patch("app.infrastructure.database.graph.driver.is_graph_enabled", return_value=True), \
             patch("app.infrastructure.database.graph.driver.get_graph_db", AsyncMock(return_value=bad_driver)):

            result = await delete_project(123)

        assert result.status == "success"
        mock_session.delete.assert_awaited_once_with(mock_repo)

    @pytest.mark.asyncio
    async def test_delete_project_vector_cleanup_failure_ignored(
        self,
        mock_cloud_success,
        mock_async_session_local,
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
            result = await delete_project(123)

        assert result.status == "success"
        mock_session.delete.assert_awaited_once_with(mock_repo)

    @pytest.mark.asyncio
    async def test_delete_project_graph_disabled(
        self,
        mock_cloud_success,
        mock_async_session_local,
        mock_session,
        mock_repo,
        mock_indexing_manager,
        mock_cache,
        mock_vector_store,
    ):
        """Graph disabled → graph cleanup skipped entirely."""
        from app.api.routes.projects import delete_project

        with patch("app.infrastructure.database.graph.driver.is_graph_enabled", return_value=False), \
             patch("app.infrastructure.database.graph.driver.get_graph_db") as mock_get_db:

            result = await delete_project(123)

        mock_get_db.assert_not_called()
        assert result.status == "success"
