"""
Unit tests for Codebase Indexing Service.
Tests IndexingService, ProjectClassifier, and related components.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from app.domain.codebase.indexing.service import IndexingService
from app.domain.codebase.indexing.classifier import ProjectClassifier, ProjectType


class TestProjectClassifier:
    """Tests for ProjectClassifier."""

    @pytest.fixture
    def classifier(self):
        return ProjectClassifier()

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_classify_nonexistent_path(self, classifier):
        """Test classifying non-existent path."""
        result = classifier.classify("/nonexistent/path")
        assert result == ProjectType.UNKNOWN

    def test_classify_software_by_indicators(self, classifier, temp_dir):
        """Test classifying software project by config files."""
        # Create package.json (software indicator)
        Path(os.path.join(temp_dir, "package.json")).touch()

        result = classifier.classify(temp_dir)

        assert result == ProjectType.SOFTWARE

    def test_classify_software_by_pyproject(self, classifier, temp_dir):
        """Test classifying Python project by pyproject.toml."""
        Path(os.path.join(temp_dir, "pyproject.toml")).touch()

        result = classifier.classify(temp_dir)

        assert result == ProjectType.SOFTWARE

    def test_classify_software_by_code_files(self, classifier, temp_dir):
        """Test classifying software project by code files."""
        # Create multiple Python files
        Path(os.path.join(temp_dir, "main.py")).touch()
        Path(os.path.join(temp_dir, "utils.py")).touch()
        Path(os.path.join(temp_dir, "helpers.py")).touch()

        result = classifier.classify(temp_dir)

        assert result == ProjectType.SOFTWARE

    def test_classify_content_project(self, classifier, temp_dir):
        """Test classifying content project."""
        # Create only markdown files
        Path(os.path.join(temp_dir, "README.md")).touch()
        Path(os.path.join(temp_dir, "docs.md")).touch()

        result = classifier.classify(temp_dir)

        assert result == ProjectType.CONTENT

    def test_classify_empty_directory(self, classifier, temp_dir):
        """Test classifying empty directory."""
        result = classifier.classify(temp_dir)

        # Empty directory should be classified as CONTENT
        assert result == ProjectType.CONTENT

    def test_classify_with_nested_code(self, classifier, temp_dir):
        """Test classifying project with code in subdirectories."""
        # Create nested structure
        src_dir = os.path.join(temp_dir, "src")
        os.makedirs(src_dir)
        Path(os.path.join(src_dir, "module.py")).touch()
        Path(os.path.join(src_dir, "main.py")).touch()
        Path(os.path.join(src_dir, "utils.py")).touch()

        result = classifier.classify(temp_dir)

        assert result == ProjectType.SOFTWARE

    def test_classify_error_handling(self, classifier):
        """Test error handling during classification."""
        with patch("os.listdir", side_effect=PermissionError("Access denied")):
            result = classifier.classify("/some/path")

        assert result == ProjectType.UNKNOWN

    def test_global_classifier_instance(self):
        """Test that global classifier instance exists."""
        from app.domain.codebase.indexing.classifier import project_classifier

        assert project_classifier is not None
        assert isinstance(project_classifier, ProjectClassifier)


class TestIndexingService:
    """Tests for IndexingService."""

    @pytest.fixture
    def indexing_service(self):
        with patch("app.domain.codebase.indexing.service.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock()
            mock_session.return_value.__aexit__ = AsyncMock()
            service = IndexingService()
            return service

    @pytest.mark.asyncio
    async def test_get_repo_by_path_found(self, indexing_service):
        """Test getting existing repository by path."""
        mock_repo = MagicMock()
        mock_repo.local_path = "/test/repo"

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = mock_repo
            mock_session.execute.return_value = mock_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await indexing_service.get_repo_by_path("/test/repo")

            assert result == mock_repo

    @pytest.mark.asyncio
    async def test_get_repo_by_path_not_found(self, indexing_service):
        """Test getting non-existent repository."""
        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_session.execute.return_value = mock_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await indexing_service.get_repo_by_path("/nonexistent/repo")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_repo_existing(self, indexing_service):
        """Test getting existing repository."""
        mock_repo = MagicMock()
        mock_repo.local_path = "/test/repo"

        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = mock_repo
            mock_session.execute.return_value = mock_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await indexing_service.get_or_create_repo("/test/repo", "test-repo")

            assert result == mock_repo

    @pytest.mark.asyncio
    async def test_get_or_create_repo_new_with_project_id(self, indexing_service):
        """Test creating new repository with project_id."""
        with patch.object(indexing_service, 'session_factory') as mock_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_session.execute.return_value = mock_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await indexing_service.get_or_create_repo(
                "/test/repo", "test-repo", project_id=123
            )

            # Should create repo with SYNCED status
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_create_repo_new_without_project_id(self, indexing_service):
        """Test creating new repository without project_id."""
        with patch.object(indexing_service, 'session_factory') as mock_factory, \
             patch("app.domain.codebase.indexing.service.evocloud_manager") as mock_cloud:
            # Mock evocloud to return no matching projects
            mock_cloud.scan_projects = AsyncMock(return_value=[])

            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_session.execute.return_value = mock_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await indexing_service.get_or_create_repo("/test/repo", "test-repo")

            # Should create repo with PENDING_CREATION status
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

    def test_service_initialization(self):
        """Test IndexingService initialization."""
        with patch("app.domain.codebase.indexing.service.AsyncSessionLocal"):
            service = IndexingService()

            assert service.file_preparer is not None
            assert service.content_indexer is not None
            assert service.sql_persister is not None
            assert service.graph_syncer is not None
            assert service.extractor is not None
            assert service.embedder is not None


class TestIndexingComponents:
    """Tests for indexing components."""

    def test_file_preparer_initialization(self):
        """Test FilePreparer initialization."""
        from app.domain.codebase.indexing.components.file_preparer import FilePreparer

        preparer = FilePreparer()
        assert preparer is not None

    def test_content_indexer_initialization(self):
        """Test ContentIndexer initialization."""
        from app.domain.codebase.indexing.components.content_indexer import ContentIndexer
        from app.domain.codebase.indexing.extractors.treesitter_extractor import TreeSitterExtractor
        from app.infrastructure.embeddings.base import BaseEmbedder

        extractor = TreeSitterExtractor()
        # Mock embedder
        mock_embedder = MagicMock(spec=BaseEmbedder)
        indexer = ContentIndexer(extractor, mock_embedder)

        assert indexer.extractor == extractor
        assert indexer.embedder == mock_embedder

    def test_sql_persister_initialization(self):
        """Test SQLPersister initialization."""
        from app.domain.codebase.indexing.components.sql_persister import SQLPersister

        persister = SQLPersister()
        assert persister is not None

    def test_graph_syncer_initialization(self):
        """Test GraphSyncer initialization."""
        from app.domain.codebase.indexing.components.graph_syncer import GraphSyncer

        syncer = GraphSyncer()
        assert syncer is not None
