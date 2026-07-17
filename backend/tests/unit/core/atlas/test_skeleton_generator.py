"""Unit tests for P2.3: AppMapSkeletonGenerator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.atlas.source.skeleton import (
    generate_app_map_skeleton,
    get_or_create_app_map_skeleton,
)
from app.core.atlas.source.skeleton.generator import AppMapSkeletonGenerator


class _AsyncSessionScope:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass

    def __call__(self):
        return self


class TestAppMapSkeletonGenerator:
    def test_constructor(self):
        gen = AppMapSkeletonGenerator()
        assert gen is not None

    @pytest.mark.asyncio
    async def test_generate_returns_list(self):
        gen = AppMapSkeletonGenerator()
        mock_session = AsyncMock()
        mock_execute = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_execute)

        result = await gen.generate(project_id=1, repo_id=1, session=mock_session, force=False)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_or_create_app_map_skeleton_no_active_repo(self):
        mock_session = AsyncMock()
        mock_execute = AsyncMock()
        mock_scalar = MagicMock()
        mock_scalar.one_or_none.return_value = None
        mock_execute.scalar = MagicMock(return_value=mock_scalar)
        mock_session.execute = AsyncMock(return_value=mock_execute)

        with patch("app.core.atlas.source.skeleton.session_scope", _AsyncSessionScope(mock_session)):
            result = await get_or_create_app_map_skeleton(project_id=999)
            assert result == []

    @pytest.mark.asyncio
    async def test_generate_app_map_skeleton_returns_list(self):
        result = await generate_app_map_skeleton(
            project_id=999, repo_id=999, force=False,
        )
        assert isinstance(result, list)
