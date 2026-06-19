from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.codebase.indexing.manager import IndexingManager


class TestIndexingManagerRepoKeys:
    """Tests that IndexingManager uses repo_id as the internal scheduling key."""

    @pytest.fixture
    def manager(self):
        return IndexingManager()

    @pytest.mark.asyncio
    async def test_dispatch_repo_index_uses_repo_id(self, manager):
        with patch(
            "app.domain.codebase.indexing.manager._set_indexing_status",
            new_callable=AsyncMock,
        ) as mock_set_status, patch(
            "app.domain.codebase.indexing.manager._clear_cancel_flag",
            new_callable=AsyncMock,
        ), patch(
            "app.domain.codebase.indexing.tasks.run_full_indexing_task"
        ) as mock_task:
            mock_task.delay = MagicMock()

            await manager._dispatch_repo_index(55, rebuild=True)

        mock_task.delay.assert_called_once_with(55, True)
        mock_set_status.assert_awaited_once_with(55, "queued")

    @pytest.mark.asyncio
    async def test_cancel_repo_index_sets_persistent_flag(self, manager):
        with patch(
            "app.domain.codebase.indexing.manager._request_cancel",
            new_callable=AsyncMock,
        ) as mock_request_cancel:
            await manager.cancel_repo_index(55)

        mock_request_cancel.assert_awaited_once_with(55)
        assert manager.get_repo_status(55) == "cancelled"

    @pytest.mark.asyncio
    async def test_check_cancelled_reads_persistent_flag(self, manager):
        with patch(
            "app.domain.codebase.indexing.manager._is_cancel_requested",
            new_callable=AsyncMock,
            return_value=True,
        ):
            cancelled = await manager._check_cancelled(55)

        assert cancelled is True
        assert manager.get_repo_status(55) == "cancelled"

    @pytest.mark.asyncio
    async def test_trigger_full_index_repo_updates_status_by_repo_id(self, manager):
        repo = MagicMock()
        repo.id = 55
        repo.project_id = 101
        repo.local_path = "/tmp/ws/proj"
        repo.relative_path = None
        repo.sync_status = "SYNCED"
        repo.name = "proj"
        repo.indexing_status = "pending"

        fake_service = AsyncMock()

        class FakeScope:
            async def __aenter__(self):
                class FakeSession:
                    async def get(self, model, obj_id):
                        return repo
                return FakeSession()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with patch(
            "app.domain.codebase.indexing.manager.session_scope", FakeScope
        ), patch(
            "app.domain.codebase.indexing.manager._set_indexing_status",
            new_callable=AsyncMock,
        ) as mock_set_status, patch(
            "app.domain.codebase.indexing.manager._clear_cancel_flag",
            new_callable=AsyncMock,
        ), patch(
            "app.domain.codebase.indexing.manager.IndexingService",
            return_value=fake_service,
        ), patch(
            "app.domain.codebase.indexing.manager.os.path.isdir", return_value=True
        ), patch.object(
            manager, "_update_indexing_status", new_callable=AsyncMock
        ) as mock_update_status:
            await manager.trigger_full_index_repo(55)

        fake_service.index_repository.assert_awaited_once_with("/tmp/ws/proj", 55, force=False)
        mock_set_status.assert_any_await(55, "indexing")
        mock_update_status.assert_awaited_with(55, "completed")

    @pytest.mark.asyncio
    async def test_dispatch_full_index_no_repo_logs_warning(self, manager):
        captured_coro = None

        def capture_create_task(coro):
            nonlocal captured_coro
            captured_coro = coro
            return MagicMock()

        with patch(
            "app.domain.codebase.indexing.manager.resolve_project_to_repo",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            manager, "_dispatch_repo_index", new_callable=AsyncMock
        ) as mock_dispatch:

            with patch("asyncio.create_task", side_effect=capture_create_task):
                manager.dispatch_full_index(101)

            assert captured_coro is not None
            await captured_coro

        mock_dispatch.assert_not_awaited()
