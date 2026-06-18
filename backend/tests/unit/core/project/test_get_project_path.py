import json
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.constants import DEFAULT_PROJECT_ID
from app.core.project.utils import get_project_path


class TestGetProjectPath:
    """Unit tests for get_project_path resolution order."""

    @pytest.fixture
    def workspace(self):
        """Create a temporary workspace with a single project."""
        tmp = tempfile.mkdtemp(prefix="test_get_project_path_")
        os.makedirs(os.path.join(tmp, "project_x", ".evoloop"), exist_ok=True)
        with open(
            os.path.join(tmp, "project_x", ".evoloop", "project.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump({"project_id": 101, "name": "project_x"}, f)
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    @pytest.fixture
    def mock_repo(self):
        """Minimal Repository mock for fallback tests."""
        repo = MagicMock()
        repo.id = 1
        repo.project_id = 101
        repo.local_path = None
        repo.relative_path = "project_x"
        return repo

    @pytest.mark.asyncio
    async def test_default_project_id_returns_workspace_root(self):
        with patch(
            "app.core.project.utils._get_workspace_root",
            return_value="/tmp/workspace",
        ):
            path = await get_project_path(DEFAULT_PROJECT_ID)
            assert path == "/tmp/workspace"

    @pytest.mark.asyncio
    async def test_local_index_authoritative(self, workspace):
        with patch(
            "app.core.project.utils._get_workspace_root",
            return_value=workspace,
        ):
            path = await get_project_path(101)
            assert path == os.path.join(workspace, "project_x")

    @pytest.mark.asyncio
    async def test_relative_path_fallback(self, workspace, mock_repo):
        async def fake_execute(_stmt):
            class FakeResult:
                def scalar_one_or_none(self):
                    return mock_repo
            return FakeResult()

        class FakeSession:
            async def execute(self, stmt):
                return await fake_execute(stmt)

        class FakeScope:
            async def __aenter__(self):
                return FakeSession()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with patch(
            "app.core.project.utils._get_workspace_root",
            return_value=workspace,
        ), patch(
            "app.core.project.utils.local_project_index.get_path",
            return_value=None,
        ), patch(
            "app.core.project.utils.session_scope",
            FakeScope,
        ), patch(
            "app.core.project.utils.os.path.isdir",
            return_value=True,
        ):
            path = await get_project_path(101)
            assert path == os.path.join(workspace, "project_x")

    @pytest.mark.asyncio
    async def test_local_path_fallback(self, workspace, mock_repo):
        mock_repo.relative_path = None
        mock_repo.local_path = os.path.join(workspace, "project_x")

        async def fake_execute(_stmt):
            class FakeResult:
                def scalar_one_or_none(self):
                    return mock_repo
            return FakeResult()

        class FakeSession:
            async def execute(self, stmt):
                return await fake_execute(stmt)

        class FakeScope:
            async def __aenter__(self):
                return FakeSession()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with patch(
            "app.core.project.utils._get_workspace_root",
            return_value=workspace,
        ), patch(
            "app.core.project.utils.local_project_index.get_path",
            return_value=None,
        ), patch(
            "app.core.project.utils.session_scope",
            FakeScope,
        ), patch(
            "app.core.project.utils.os.path.isdir",
            return_value=True,
        ):
            path = await get_project_path(101)
            assert path == os.path.join(workspace, "project_x")

    @pytest.mark.asyncio
    async def test_returns_empty_when_unresolvable(self, workspace):
        class FailingScope:
            async def __aenter__(self):
                raise Exception("DB unavailable")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with patch(
            "app.core.project.utils._get_workspace_root",
            return_value=workspace,
        ), patch(
            "app.core.project.utils.local_project_index.get_path",
            return_value=None,
        ), patch(
            "app.infrastructure.database.sql.database.session_scope",
            FailingScope,
        ):
            path = await get_project_path(999)
            assert path == ""



