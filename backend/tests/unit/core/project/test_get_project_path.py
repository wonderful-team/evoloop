import json
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.constants import DEFAULT_PROJECT_ID
from app.core.project.utils import get_project_path, resolve_project_to_repo


def _make_fake_session_scope(get_return=None, all_return=None):
    """Build a fake session_scope that returns a session with get()/execute()."""

    class FakeSession:
        async def get(self, model, obj_id):
            return get_return

        async def execute(self, stmt):
            class FakeResult:
                def scalars(self):
                    return self

                def all(self):
                    return all_return or []

            return FakeResult()

    class FakeScope:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    return FakeScope


class TestResolveProjectToRepo:
    """Unit tests for resolve_project_to_repo."""

    @pytest.mark.asyncio
    async def test_default_project_id_returns_none(self):
        with patch("app.core.project.utils._get_workspace_root", return_value="/tmp/ws"):
            repo = await resolve_project_to_repo(DEFAULT_PROJECT_ID)
            assert repo is None

    @pytest.mark.asyncio
    async def test_local_repo_id_trusts_json_and_verifies_db(self):
        repo_mock = MagicMock()
        repo_mock.id = 7
        repo_mock.sync_status = "SYNCED"

        with patch(
            "app.core.project.utils._get_workspace_root", return_value="/tmp/ws"
        ), patch(
            "app.core.project.utils.local_project_index.get_entry",
            return_value=MagicMock(path="/tmp/ws/proj", repo_id=7, project_id=101),
        ), patch(
            "app.core.project.utils.session_scope",
            _make_fake_session_scope(get_return=repo_mock),
        ):
            repo = await resolve_project_to_repo(101)
            assert repo is repo_mock

    @pytest.mark.asyncio
    async def test_no_local_repo_id_falls_back_to_db_query(self):
        repo_mock = MagicMock()
        repo_mock.id = 8
        repo_mock.sync_status = "SYNCED"
        repo_mock.local_path = "/tmp/ws/proj"
        repo_mock.relative_path = None

        with patch(
            "app.core.project.utils._get_workspace_root", return_value="/tmp/ws"
        ), patch(
            "app.core.project.utils.local_project_index.get_entry",
            return_value=MagicMock(path="/tmp/ws/proj", repo_id=None, project_id=101),
        ), patch(
            "app.core.project.utils.session_scope",
            _make_fake_session_scope(all_return=[repo_mock]),
        ):
            repo = await resolve_project_to_repo(101)
            assert repo is repo_mock

    @pytest.mark.asyncio
    async def test_returns_none_when_no_local_or_db_match(self):
        with patch(
            "app.core.project.utils._get_workspace_root", return_value="/tmp/ws"
        ), patch(
            "app.core.project.utils.local_project_index.get_entry",
            return_value=None,
        ), patch(
            "app.core.project.utils.session_scope",
            _make_fake_session_scope(all_return=[]),
        ):
            repo = await resolve_project_to_repo(101)
            assert repo is None


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



