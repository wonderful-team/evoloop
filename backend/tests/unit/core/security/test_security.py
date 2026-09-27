"""Unit tests for command execution security helpers."""

from __future__ import annotations

import os

import pytest

from app.core.security.command import has_workspace_escape


@pytest.fixture
def roots(tmp_path):
    """Provide three safe directories for tests."""
    project = tmp_path / "project"
    project.mkdir()
    evoloop = tmp_path / ".evoloop"
    evoloop.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return {
        "project": str(project),
        "evoloop": str(evoloop),
        "workspace": str(workspace),
    }


class TestHasWorkspaceEscape:
    def test_cd_inside_working_dir_allowed(self, roots):
        assert (
            has_workspace_escape(
                "cd subdir && ls",
                working_dir=roots["project"],
                allowed_roots=[roots["project"], roots["evoloop"], roots["workspace"]],
            )
            is None
        )

    def test_cd_to_evoloop_allowed(self, roots):
        assert (
            has_workspace_escape(
                f"cd {roots['evoloop']} && ls",
                working_dir=roots["project"],
                allowed_roots=[roots["project"], roots["evoloop"], roots["workspace"]],
            )
            is None
        )

    def test_cd_to_workspace_subdir_allowed(self, roots):
        sub = os.path.join(roots["workspace"], "sub")
        os.makedirs(sub, exist_ok=True)
        assert (
            has_workspace_escape(
                f"cd {sub} && ls",
                working_dir=roots["project"],
                allowed_roots=[roots["project"], roots["evoloop"], roots["workspace"]],
            )
            is None
        )

    def test_cd_outside_allowed_roots_blocked(self, roots):
        outside = roots["project"] + "_outside"
        os.makedirs(outside, exist_ok=True)
        result = has_workspace_escape(
            f"cd {outside} && ls",
            working_dir=roots["project"],
            allowed_roots=[roots["project"], roots["evoloop"], roots["workspace"]],
        )
        assert result is not None

    def test_cd_to_home_blocked_without_allowed_roots(self, roots):
        result = has_workspace_escape(
            "cd ~/.evoloop && ls",
            working_dir=roots["project"],
        )
        assert result is not None

    def test_command_without_cd_allowed(self, roots):
        assert (
            has_workspace_escape(
                "python script.py --output data.json",
                working_dir=roots["project"],
                allowed_roots=[roots["project"], roots["evoloop"]],
            )
            is None
        )

    def test_pushd_to_evoloop_allowed(self, roots):
        assert (
            has_workspace_escape(
                f"pushd {roots['evoloop']} && ls && popd",
                working_dir=roots["project"],
                allowed_roots=[roots["project"], roots["evoloop"]],
            )
            is None
        )

    def test_relative_cd_resolved_against_working_dir(self, roots):
        sub = os.path.join(roots["project"], "scripts")
        os.makedirs(sub, exist_ok=True)
        assert (
            has_workspace_escape(
                "cd scripts && python run.py",
                working_dir=roots["project"],
                allowed_roots=[roots["project"], roots["evoloop"]],
            )
            is None
        )

    def test_parent_traversal_blocked(self, roots):
        result = has_workspace_escape(
            "cd ../.. && ls",
            working_dir=roots["project"],
            allowed_roots=[roots["project"], roots["evoloop"]],
        )
        assert result is not None
