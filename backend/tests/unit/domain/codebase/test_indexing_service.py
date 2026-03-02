"""
Unit tests for Indexing Service.
Tests the file indexing pipeline using specialized components.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from app.domain.codebase.indexing.service import IndexingService


class TestIndexingService:
    """Tests for IndexingService class."""

    @pytest.fixture
    def indexing_service(self):
        """Create an IndexingService instance with mocked dependencies."""
        with patch("app.domain.codebase.indexing.service.AsyncSessionLocal") as mock_session_factory:
            with patch("app.domain.codebase.indexing.service.TreeSitterExtractor"):
                with patch("app.domain.codebase.indexing.service.EmbedderFactory"):
                    with patch("app.domain.codebase.indexing.service.FilePreparer"):
                        with patch("app.domain.codebase.indexing.service.ContentIndexer"):
                            with patch("app.domain.codebase.indexing.service.SQLPersister"):
                                with patch("app.domain.codebase.indexing.service.GraphSyncer"):
                                    service = IndexingService()
                                    yield service

    @pytest.mark.asyncio
    async def test_get_repo_by_path_found(self, indexing_service):
        """Test getting repository by path when it exists."""
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.local_path = "/test/repo"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_repo

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await indexing_service.get_repo_by_path("/test/repo")

            assert result == mock_repo
            mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_repo_by_path_not_found(self, indexing_service):
        """Test getting repository by path when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await indexing_service.get_repo_by_path("/nonexistent/repo")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_repo_existing(self, indexing_service):
        """Test get_or_create_repo returns existing repo."""
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.local_path = "/test/repo"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_repo

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await indexing_service.get_or_create_repo("/test/repo", "test-repo")

            assert result == mock_repo
            mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_create_repo_new(self, indexing_service):
        """Test get_or_create_repo creates new repo."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with patch("app.domain.codebase.indexing.service.evocloud_manager") as mock_evocloud:
            mock_evocloud.scan_projects.return_value = []

            with patch.object(indexing_service, 'session_factory') as mock_factory:
                mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await indexing_service.get_or_create_repo("/test/repo", "test-repo")

                mock_session.add.assert_called_once()
                mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_repos(self, indexing_service):
        """Test getting all repositories."""
        mock_repos = [MagicMock(id=1), MagicMock(id=2)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_repos

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await indexing_service.get_all_repos()

            assert result == mock_repos
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_index_file_success(self, indexing_service):
        """Test successful file indexing."""
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.local_path = "/test/repo"

        mock_session = AsyncMock()
        mock_session.get.return_value = mock_repo

        # Mock file preparer
        prepared = MagicMock()
        prepared.content = "def test(): pass"
        prepared.rel_path = "test.py"
        indexing_service.file_preparer.prepare = AsyncMock(return_value=prepared)
        indexing_service.file_preparer.create_or_update_source_file = AsyncMock(return_value=MagicMock(id=1))

        # Mock content indexer
        indexed = MagicMock()
        indexed.documents = []
        indexed.entities = []
        indexed.relations = []
        indexing_service.content_indexer.index = AsyncMock(return_value=indexed)

        # Mock persisters
        indexing_service.sql_persister.clear_old_data = AsyncMock()
        indexing_service.sql_persister.persist = AsyncMock(return_value={})
        indexing_service.graph_syncer.sync = AsyncMock()

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            await indexing_service.index_file("/test/repo/test.py", 1)

            indexing_service.file_preparer.prepare.assert_called_once()
            indexing_service.content_indexer.index.assert_called_once()
            indexing_service.sql_persister.persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_file_repo_not_found(self, indexing_service):
        """Test indexing when repo not found."""
        mock_session = AsyncMock()
        mock_session.get.return_value = None

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            await indexing_service.index_file("/test/repo/test.py", 999)

            indexing_service.file_preparer.prepare.assert_not_called()

    @pytest.mark.asyncio
    async def test_index_file_skip_when_not_prepared(self, indexing_service):
        """Test skipping when file preparer returns None."""
        mock_repo = MagicMock()
        mock_repo.id = 1

        mock_session = AsyncMock()
        mock_session.get.return_value = mock_repo

        indexing_service.file_preparer.prepare = AsyncMock(return_value=None)

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            await indexing_service.index_file("/test/repo/test.py", 1)

            indexing_service.content_indexer.index.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_file_success(self, indexing_service):
        """Test successful file removal."""
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.local_path = "/test/repo"
        mock_repo.project_id = 1

        mock_source_file = MagicMock()
        mock_source_file.id = 1

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_source_file

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.get.return_value = mock_repo

        indexing_service.sql_persister.clear_old_data = AsyncMock()

        with patch("app.domain.codebase.indexing.service.get_graph_db") as mock_get_graph:
            mock_driver = AsyncMock()
            mock_get_graph.return_value = mock_driver

            with patch.object(indexing_service, 'session_factory') as mock_factory:
                mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

                await indexing_service.remove_file("/test/repo/test.py", 1)

                mock_session.delete.assert_called_once_with(mock_source_file)
                mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_move_file_success(self, indexing_service):
        """Test successful file move."""
        with patch.object(indexing_service, 'remove_file') as mock_remove:
            with patch.object(indexing_service, 'index_file') as mock_index:
                with patch("os.path.exists", return_value=True):
                    await indexing_service.move_file("/src/file.py", "/dest/file.py", 1)

                    mock_remove.assert_called_once_with("/src/file.py", 1)
                    mock_index.assert_called_once_with("/dest/file.py", 1)

    @pytest.mark.asyncio
    async def test_move_file_dest_not_exists(self, indexing_service):
        """Test move when destination doesn't exist."""
        with patch.object(indexing_service, 'remove_file') as mock_remove:
            with patch.object(indexing_service, 'index_file') as mock_index:
                with patch("os.path.exists", return_value=False):
                    await indexing_service.move_file("/src/file.py", "/dest/file.py", 1)

                    mock_remove.assert_called_once()
                    mock_index.assert_not_called()


class TestIndexingServiceErrorHandling:
    """Error handling tests for IndexingService."""

    @pytest.fixture
    def indexing_service(self):
        """Create an IndexingService instance with mocked dependencies."""
        with patch("app.domain.codebase.indexing.service.AsyncSessionLocal"):
            with patch("app.domain.codebase.indexing.service.TreeSitterExtractor"):
                with patch("app.domain.codebase.indexing.service.EmbedderFactory"):
                    with patch("app.domain.codebase.indexing.service.FilePreparer"):
                        with patch("app.domain.codebase.indexing.service.ContentIndexer"):
                            with patch("app.domain.codebase.indexing.service.SQLPersister"):
                                with patch("app.domain.codebase.indexing.service.GraphSyncer"):
                                    yield IndexingService()

    @pytest.mark.asyncio
    async def test_index_file_exception_handling(self, indexing_service):
        """Test exception handling during file indexing."""
        mock_repo = MagicMock()
        mock_repo.id = 1

        mock_session = AsyncMock()
        mock_session.get.return_value = mock_repo

        indexing_service.file_preparer.prepare = AsyncMock(side_effect=Exception("Prepare failed"))

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            # Should not raise
            await indexing_service.index_file("/test/repo/test.py", 1)

            mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_file_exception_handling(self, indexing_service):
        """Test exception handling during file removal."""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Execute failed")

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            # Should not raise
            await indexing_service.remove_file("/test/repo/test.py", 1)

            mock_session.rollback.assert_called_once()
