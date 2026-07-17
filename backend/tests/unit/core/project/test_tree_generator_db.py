"""Unit tests for P1.1: AnnotatedTreeGenerator DB assembly path."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.project.tree_generator import AnnotatedTreeGenerator


class _AsyncSessionScope:
    def __init__(self, session):
        self._session = session
    async def __aenter__(self):
        return self._session
    async def __aexit__(self, *args):
        pass
    def __call__(self):
        return self


@pytest.fixture
def generator():
    gen = AnnotatedTreeGenerator(
        root_path="/fake/project",
        max_depth=5,
        with_symbols=True,
    )
    gen.file_filter = MagicMock()
    gen.file_filter.should_include.return_value = True
    return gen


def _make_session(source_files=None, repo=None):
    session = AsyncMock()
    exec_mock = AsyncMock()
    scalars_mock = MagicMock()
    if source_files is not None:
        scalars_mock.all.return_value = source_files
    if repo is not None:
        scalars_mock.first.return_value = repo
    exec_mock.scalars = MagicMock(return_value=scalars_mock)
    session.execute = AsyncMock(return_value=exec_mock)
    return session


class TestTreeGeneratorDBAssembly:
    @pytest.mark.asyncio
    async def test_build_from_db_returns_node(self, generator):
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.local_path = "/fake/project"
        mock_sf = MagicMock()
        mock_sf.path = "src/main.py"
        mock_sf.chunks = []

        session = _make_session(source_files=[mock_sf])
        with patch.object(generator, "_find_repository_by_path", AsyncMock(return_value=mock_repo)):
            with patch.object(generator, "_is_path_ignored", return_value=False):
                with patch("app.core.project.tree_generator.session_scope", _AsyncSessionScope(session)):
                    root = await generator._build_tree_from_db(set())
                    assert root is not None
                    assert root.name == "project"
                    assert root.type == "dir"

    @pytest.mark.asyncio
    async def test_build_from_db_returns_none_when_no_repo(self, generator):
        session = _make_session()
        with patch.object(generator, "_find_repository_by_path", AsyncMock(return_value=None)):
            with patch("app.core.project.tree_generator.session_scope", _AsyncSessionScope(session)):
                root = await generator._build_tree_from_db(set())
                assert root is None

    @pytest.mark.asyncio
    async def test_build_from_db_returns_none_when_no_source_files(self, generator):
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.local_path = "/fake/project"
        session = _make_session(source_files=[])
        with patch.object(generator, "_find_repository_by_path", AsyncMock(return_value=mock_repo)):
            with patch("app.core.project.tree_generator.session_scope", _AsyncSessionScope(session)):
                root = await generator._build_tree_from_db(set())
                assert root is None

    def test_constructor_defaults(self):
        gen = AnnotatedTreeGenerator(root_path="/tmp")
        assert gen.max_depth == 3
        assert gen.with_symbols is True
        assert gen.file_limit == 50
