"""
Unit tests for Project Sync Service.
Tests project synchronization with local filesystem and cloud.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from app.domain.project.sync_service import ProjectSyncService


class TestProjectSyncService:
    """Tests for ProjectSyncService class."""

    @pytest.fixture
    def sync_service(self):
        """Create a ProjectSyncService instance with mocked dependencies."""
        with patch("app.domain.project.sync_service.IndexingService") as mock_indexing:
            yield ProjectSyncService()

    @pytest.mark.asyncio
    async def test_handle_project_created_new(self, sync_service):
        """Test handling new project creation."""
        with patch.object(sync_service._indexing_service, 'get_repo_by_path', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            with patch("app.domain.project.sync_service.AsyncSessionLocal") as mock_session_factory:
                mock_session = AsyncMock()
                mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

                with patch("app.domain.project.sync_service.system_bus") as mock_bus:
                    mock_bus.publish = AsyncMock()

                    await sync_service.handle_project_created("/projects/new-project")

                    mock_session.add.assert_called_once()
                    mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_project_created_existing(self, sync_service):
        """Test handling project creation when repo already exists."""
        with patch.object(sync_service._indexing_service, 'get_repo_by_path', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MagicMock(id=1)

            with patch("app.domain.project.sync_service.AsyncSessionLocal") as mock_session_factory:
                mock_session = AsyncMock()

                await sync_service.handle_project_created("/projects/existing")

                mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_project_created_auto_ignore_hidden(self, sync_service):
        """Test auto-ignoring hidden directories."""
        with patch.object(sync_service._indexing_service, 'get_repo_by_path') as mock_get:
            mock_get.return_value = None

            # Should auto-ignore hidden directories
            await sync_service.handle_project_created("/projects/.hidden")

            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_project_created_auto_ignore_system_dirs(self, sync_service):
        """Test auto-ignoring system directories."""
        with patch.object(sync_service._indexing_service, 'get_repo_by_path') as mock_get:
            mock_get.return_value = None

            # Should auto-ignore system directories
            await sync_service.handle_project_created("/projects/node_modules")

            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_import_project_success(self, sync_service):
        """Test successful project import."""
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.name = "test-project"
        mock_repo.local_path = "/projects/test"
        mock_repo.project_id = None
        mock_repo.sync_status = "DETECTED"

        with patch("app.domain.project.sync_service.AsyncSessionLocal") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_repo
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("app.domain.project.sync_service.system_bus") as mock_bus:
                mock_bus.publish = AsyncMock()

                # Patch the task import at module level
                with patch.dict("sys.modules", {"app.domain.project.sync_tasks": MagicMock(sync_project_to_cloud_task=MagicMock())}):
                    result = await sync_service.import_project(1)

                    assert result == mock_repo
                    assert mock_repo.sync_status == "PENDING_CREATION"
                    mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_import_project_not_found(self, sync_service):
        """Test importing non-existent project."""
        with patch("app.domain.project.sync_service.AsyncSessionLocal") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session.get.return_value = None
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="not found"):
                await sync_service.import_project(999)

    @pytest.mark.asyncio
    async def test_import_project_already_imported(self, sync_service):
        """Test importing already imported project."""
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.name = "test-project"
        mock_repo.sync_status = "SYNCED"

        with patch("app.domain.project.sync_service.AsyncSessionLocal") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_repo
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await sync_service.import_project(1)

            # Should return existing repo without changes
            assert result == mock_repo

    @pytest.mark.asyncio
    async def test_ignore_project_success(self, sync_service):
        """Test successful project ignore."""
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.name = "test-project"
        mock_repo.sync_status = "DETECTED"

        with patch("app.domain.project.sync_service.AsyncSessionLocal") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_repo
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            await sync_service.ignore_project(1)

            assert mock_repo.sync_status == "IGNORED"
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_unignore_project_success(self, sync_service):
        """Test successful project unignore."""
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.name = "test-project"
        mock_repo.sync_status = "IGNORED"

        with patch("app.domain.project.sync_service.AsyncSessionLocal") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_repo
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await sync_service.unignore_project(1)

            assert result.sync_status == "DETECTED"
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_detected_projects(self, sync_service):
        """Test getting detected projects."""
        mock_repos = [
            MagicMock(id=1, sync_status="DETECTED"),
            MagicMock(id=2, sync_status="DETECTED"),
        ]

        with patch("app.domain.project.sync_service.AsyncSessionLocal") as mock_session_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = mock_repos
            mock_session.execute.return_value = mock_result
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await sync_service.get_detected_projects()

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_ignored_projects(self, sync_service):
        """Test getting ignored projects."""
        mock_repos = [
            MagicMock(id=1, sync_status="IGNORED"),
        ]

        with patch("app.domain.project.sync_service.AsyncSessionLocal") as mock_session_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = mock_repos
            mock_session.execute.return_value = mock_result
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await sync_service.get_ignored_projects()

            assert len(result) == 1



class TestProjectSyncServiceEdgeCases:
    """Edge case tests for ProjectSyncService."""

    @pytest.fixture
    def sync_service(self):
        """Create a ProjectSyncService instance."""
        with patch("app.domain.project.sync_service.IndexingService"):
            yield ProjectSyncService()

    @pytest.mark.asyncio
    async def test_should_auto_ignore_hidden(self, sync_service):
        """Test auto-ignore for hidden directories."""
        assert sync_service._should_auto_ignore("/path/.hidden") is True
        assert sync_service._should_auto_ignore("/path/.git") is True

    @pytest.mark.asyncio
    async def test_should_auto_ignore_system_dirs(self, sync_service):
        """Test auto-ignore for system directories."""
        assert sync_service._should_auto_ignore("/path/node_modules") is True
        assert sync_service._should_auto_ignore("/path/__pycache__") is True
        assert sync_service._should_auto_ignore("/path/venv") is True

    @pytest.mark.asyncio
    async def test_should_not_auto_ignore_regular(self, sync_service):
        """Test regular directories are not ignored."""
        assert sync_service._should_auto_ignore("/path/my-project") is False
        assert sync_service._should_auto_ignore("/path/src") is False

    @pytest.mark.asyncio
    async def test_reconcile_projects_invalid_root(self, sync_service):
        """Test reconcile with invalid root path."""
        with patch("os.path.exists", return_value=False):
            # Should not raise
            await sync_service.reconcile_projects("/nonexistent")

    @pytest.mark.asyncio
    async def test_handle_project_deleted_no_repo(self, sync_service):
        """Test deleting project that has no repo record."""
        with patch.object(sync_service._indexing_service, 'get_repo_by_path') as mock_get:
            mock_get.return_value = None

            with patch("app.domain.project.sync_service.system_bus") as mock_bus:
                mock_bus.publish = AsyncMock()

                # Should not raise
                await sync_service.handle_project_deleted("/projects/nonexistent")

                # Should still publish event
                mock_bus.publish.assert_called_once()
