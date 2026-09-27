"""Unit tests for app.core.security.command."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.core.security.command import (
    _is_under_any_root,
    _resolve_cd_target,
    has_workspace_escape,
    is_dangerous_command,
)


class TestIsDangerousCommand:
    def test_rm_rf_root_is_dangerous(self):
        dangerous, reason = is_dangerous_command("rm -rf /")
        assert dangerous is True
        assert "destructive rm on root" in reason

    def test_modifying_shell_config_is_dangerous(self):
        dangerous, reason = is_dangerous_command("echo stuff > ~/.bashrc")
        assert dangerous is True
        assert "shell config" in reason

    def test_deep_traversal_is_dangerous(self):
        dangerous, reason = is_dangerous_command("cat ../../secret.txt")
        assert dangerous is True
        assert "directory traversal" in reason

    def test_writing_to_downloads_is_dangerous(self):
        dangerous, reason = is_dangerous_command("echo data > ~/Downloads/out.txt")
        assert dangerous is True
        assert "Downloads" in reason

    def test_safe_command_is_allowed(self):
        dangerous, reason = is_dangerous_command("python script.py")
        assert dangerous is False
        assert reason == ""


class TestResolveCdTarget:
    def test_resolves_absolute_path(self):
        assert _resolve_cd_target("/tmp", "/home") == "/tmp"

    def test_resolves_relative_path_against_base(self, tmp_path):
        base = str(tmp_path)
        assert _resolve_cd_target("subdir", base) == os.path.abspath(os.path.join(base, "subdir"))

    def test_returns_none_for_cd_dash(self):
        assert _resolve_cd_target("-", "/home") is None


class TestIsUnderAnyRoot:
    def test_under_root(self, tmp_path):
        root = str(tmp_path)
        assert _is_under_any_root(str(tmp_path / "sub"), [root]) is True

    def test_outside_root(self, tmp_path):
        root = str(tmp_path / "a")
        outside = str(tmp_path / "b")
        assert _is_under_any_root(outside, [root]) is False


class TestHasWorkspaceEscape:
    @pytest.fixture
    def roots(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        return {"project": str(project), "evoloop": str(evoloop)}

    def test_cd_inside_working_dir_allowed(self, roots):
        assert has_workspace_escape(
            "cd subdir && ls",
            working_dir=roots["project"],
            allowed_roots=[roots["project"], roots["evoloop"]],
        ) is None

    def test_cd_to_evoloop_allowed(self, roots):
        assert has_workspace_escape(
            f"cd {roots['evoloop']} && ls",
            working_dir=roots["project"],
            allowed_roots=[roots["project"], roots["evoloop"]],
        ) is None

    def test_cd_outside_allowed_roots_blocked(self, roots):
        outside = roots["project"] + "_outside"
        os.makedirs(outside, exist_ok=True)
        result = has_workspace_escape(
            f"cd {outside} && ls",
            working_dir=roots["project"],
            allowed_roots=[roots["project"], roots["evoloop"]],
        )
        assert result is not None

    def test_parent_traversal_blocked(self, roots):
        result = has_workspace_escape(
            "cd ../.. && ls",
            working_dir=roots["project"],
            allowed_roots=[roots["project"], roots["evoloop"]],
        )
        assert result is not None

    def test_command_without_cd_allowed(self, roots):
        assert has_workspace_escape(
            "python script.py",
            working_dir=roots["project"],
            allowed_roots=[roots["project"], roots["evoloop"]],
        ) is None


class TestEdgeCases:
    def test_empty_token_returns_none(self):
        assert _resolve_cd_target("", "/home") is None

    def test_is_under_any_root_skips_empty_root(self, tmp_path):
        assert _is_under_any_root(str(tmp_path), [""]) is False

    def test_legacy_behavior_blocks_cd_to_home(self, tmp_path):
        project = str(tmp_path / "project")
        os.makedirs(project, exist_ok=True)
        assert has_workspace_escape("cd ~/ && ls", working_dir=project) is not None
        assert has_workspace_escape("cd /tmp && ls", working_dir=project) is not None
        assert has_workspace_escape("cd .. && ls", working_dir=project) is not None

    def test_multi_tenant_blocks_system_dirs(self):
        with patch("app.core.security.command.settings.MULTI_TENANT_MODE", True):
            dangerous, reason = is_dangerous_command("cat /etc/passwd")
            assert dangerous is True
            assert "System directories" in reason
