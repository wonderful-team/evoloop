"""Unit tests for centralized path security helpers."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.core.config import settings
from app.core.security.path import (
    get_allowed_roots,
    is_path_safe,
    is_project_metadata_path,
    is_under_allowed_root,
)


class TestIsProjectMetadataPath:
    def test_app_data_file_is_not_metadata(self, monkeypatch, tmp_path):
        app_data = tmp_path / ".evoloop"
        app_data.mkdir()
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(app_data))
        assert is_project_metadata_path(str(app_data / "backend.db")) is False

    def test_app_data_with_tilde_is_not_metadata(self, monkeypatch):
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", "~/.evoloop")
        assert is_project_metadata_path("~/.evoloop/skills/foo/SKILL.md") is False

    def test_relative_evoloop_is_metadata(self, monkeypatch, tmp_path):
        app_data = tmp_path / ".evoloop"
        app_data.mkdir()
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(app_data))
        assert is_project_metadata_path(".evoloop/project.json") is True

    def test_project_local_evoloop_is_metadata(self, monkeypatch, tmp_path):
        app_data = tmp_path / ".evoloop"
        app_data.mkdir()
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(app_data))
        assert is_project_metadata_path("/Users/foo/project/.evoloop/project.json") is True

    def test_non_evoloop_path_is_not_metadata(self):
        assert is_project_metadata_path("/tmp/foo.txt") is False


class TestGetAllowedRoots:
    def test_includes_working_dir_app_data_and_workspace_root(self, tmp_path, monkeypatch):
        wd = tmp_path / "wd"
        wd.mkdir()
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(evoloop))
        with patch(
            "app.core.security.path.get_workspace_root", return_value=str(workspace)
        ):
            roots = get_allowed_roots(working_dir=str(wd))

        abs_roots = {os.path.abspath(r) for r in roots}
        assert os.path.abspath(str(wd)) in abs_roots
        assert os.path.abspath(str(evoloop)) in abs_roots
        assert os.path.abspath(str(workspace)) in abs_roots

    def test_includes_allowed_path_prefixes(self, tmp_path, monkeypatch):
        extra = tmp_path / "extra"
        extra.mkdir()
        monkeypatch.setattr(settings, "ALLOWED_PATH_PREFIXES", [str(extra)])
        roots = get_allowed_roots()
        assert os.path.abspath(str(extra)) in {os.path.abspath(r) for r in roots}

    def test_skips_nonexistent_directories(self, tmp_path, monkeypatch):
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(evoloop))
        with patch(
            "app.core.security.path.get_workspace_root", return_value="/does/not/exist"
        ):
            roots = get_allowed_roots()
        assert os.path.abspath(str(evoloop)) in {os.path.abspath(r) for r in roots}
        assert "/does/not/exist" not in roots


class TestIsUnderAllowedRoot:
    def test_path_under_allowed_root(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        sub = root / "sub" / "file.txt"
        assert is_under_allowed_root(str(sub), allowed_roots=[str(root)]) is True

    def test_path_outside_allowed_root(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "other" / "file.txt"
        assert is_under_allowed_root(str(outside), allowed_roots=[str(root)]) is False


class TestIsPathSafe:
    def test_relative_path_against_working_dir(self, tmp_path, monkeypatch):
        wd = tmp_path / "project"
        wd.mkdir()
        file = wd / "data.json"
        file.write_text("{}")
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(tmp_path / ".evoloop"))
        assert is_path_safe("data.json", working_dir=str(wd)) is True

    def test_absolute_path_under_app_data(self, tmp_path, monkeypatch):
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(evoloop))
        assert is_path_safe(str(evoloop / "skills" / "foo" / "SKILL.md")) is True

    def test_absolute_path_outside_all_roots_blocked(self, tmp_path, monkeypatch):
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(evoloop))
        monkeypatch.setattr(settings, "ALLOWED_PATH_PREFIXES", [])
        with patch(
            "app.core.security.path.get_workspace_root", return_value=""
        ):
            assert is_path_safe("/tmp/secret.txt") is False


class TestEdgeCases:
    def test_normalize_path_falls_back_on_oserror(self):
        from app.core.security.path import _normalize_path

        with patch("os.path.realpath", side_effect=OSError("boom")):
            result = _normalize_path("/some/path")
        assert result == os.path.abspath("/some/path")

    def test_get_allowed_roots_includes_project_path(self, tmp_path, monkeypatch):
        project = tmp_path / "project"
        project.mkdir()
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(evoloop))
        with patch(
            "app.core.security.path.get_workspace_root", return_value=""
        ), patch.object(settings, "ALLOWED_PATH_PREFIXES", []):
            roots = get_allowed_roots(project_path=str(project))
        assert os.path.abspath(str(project)) in {os.path.abspath(r) for r in roots}

    def test_is_under_allowed_root_false_when_no_roots(self):
        assert is_under_allowed_root("/any/path", allowed_roots=[]) is False

    def test_is_path_safe_false_for_empty_path(self):
        assert is_path_safe("") is False

    def test_is_path_safe_with_explicit_allowed_roots(self, tmp_path):
        root = tmp_path / "safe"
        root.mkdir()
        assert (
            is_path_safe(
                str(root / "file.txt"),
                allowed_roots=[str(root)],
            )
            is True
        )
