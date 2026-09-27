"""Unit tests for file tool path resolution."""

from __future__ import annotations

import os

import pytest

from app.core.config import settings
from app.core.file.tools import resolve_and_validate_path


@pytest.fixture
def app_data_dir(monkeypatch, tmp_path):
    """Point ``~/.evoloop`` to a temp directory for the duration of the test."""
    app_data = tmp_path / ".evoloop"
    app_data.mkdir()
    monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(app_data))
    return str(app_data)


class TestResolveAndValidatePath:
    async def test_evoloop_app_data_file_allowed(self, app_data_dir):
        target = os.path.join(app_data_dir, "skills", "foo", "SKILL.md")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        target_path = await resolve_and_validate_path(
            target,
            config={"configurable": {"working_directory": app_data_dir}},
        )
        assert os.path.abspath(target) == target_path

    async def test_evoloop_app_data_directory_allowed(self, app_data_dir):
        target_path = await resolve_and_validate_path(
            app_data_dir,
            config={"configurable": {"working_directory": app_data_dir}},
        )
        assert os.path.abspath(app_data_dir) == target_path

    async def test_project_local_evoloop_blocked(self, app_data_dir):
        project_local = "/Users/foo/project/.evoloop/project.json"
        with pytest.raises(ValueError):
            await resolve_and_validate_path(
                project_local,
                config={"configurable": {"working_directory": app_data_dir}},
            )

    async def test_relative_evoloop_under_project_working_dir_blocked(
        self, app_data_dir
    ):
        project_dir = "/tmp/project"
        with pytest.raises(ValueError):
            await resolve_and_validate_path(
                ".evoloop/project.json",
                config={"configurable": {"working_directory": project_dir}},
            )

    async def test_evoloop_app_data_with_tilde_allowed(self, app_data_dir, monkeypatch):
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", "~/.evoloop")
        target_path = await resolve_and_validate_path(
            "~/.evoloop/skills/foo/SKILL.md",
            config={"configurable": {"working_directory": "/tmp"}},
        )
        assert os.path.expanduser("~/.evoloop/skills/foo/SKILL.md") == target_path
