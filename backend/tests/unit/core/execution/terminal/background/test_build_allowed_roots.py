"""Unit tests for background command execution helpers."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.core.config import settings
from app.core.execution.terminal.background.runner import _build_allowed_roots


class TestBuildAllowedRoots:
    def test_includes_working_dir_app_data_and_workspace_root(self, tmp_path):
        wd = tmp_path / "wd"
        wd.mkdir()
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        original_app_data = settings.EVOLOOP_APP_DATA_DIR
        try:
            settings.EVOLOOP_APP_DATA_DIR = str(evoloop)
            with patch(
                "app.core.security.path.get_workspace_root",
                return_value=str(workspace),
            ):
                roots = _build_allowed_roots(str(wd))
        finally:
            settings.EVOLOOP_APP_DATA_DIR = original_app_data

        abs_roots = {os.path.abspath(r) for r in roots}
        assert os.path.abspath(str(wd)) in abs_roots
        assert os.path.abspath(str(evoloop)) in abs_roots
        assert os.path.abspath(str(workspace)) in abs_roots

    def test_skips_nonexistent_directories(self, tmp_path):
        wd = tmp_path / "wd"
        wd.mkdir()
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        # workspace_root points to a path that does not exist
        original_app_data = settings.EVOLOOP_APP_DATA_DIR
        try:
            settings.EVOLOOP_APP_DATA_DIR = str(evoloop)
            with patch(
                "app.core.security.path.get_workspace_root",
                return_value=str(tmp_path / "missing"),
            ):
                roots = _build_allowed_roots(str(wd))
        finally:
            settings.EVOLOOP_APP_DATA_DIR = original_app_data

        abs_roots = {os.path.abspath(r) for r in roots}
        assert os.path.abspath(str(wd)) in abs_roots
        assert os.path.abspath(str(evoloop)) in abs_roots
        assert os.path.abspath(str(tmp_path / "missing")) not in abs_roots

    def test_returns_app_data_even_when_working_dir_missing(self, tmp_path):
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        original_app_data = settings.EVOLOOP_APP_DATA_DIR
        try:
            settings.EVOLOOP_APP_DATA_DIR = str(evoloop)
            with patch(
                "app.core.security.path.get_workspace_root",
                return_value="",
            ):
                roots = _build_allowed_roots(None)
        finally:
            settings.EVOLOOP_APP_DATA_DIR = original_app_data

        assert os.path.abspath(str(evoloop)) in {os.path.abspath(r) for r in roots}
