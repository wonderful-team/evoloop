import json
import os
import shutil
import tempfile

import pytest

from app.core.project.local_index import LocalProjectIndex


class TestLocalProjectIndex:
    """Unit tests for LocalProjectIndex."""

    @pytest.fixture
    def workspace(self):
        """Create a temporary workspace with test projects."""
        tmp = tempfile.mkdtemp(prefix="test_workspace_")

        # project_a with project_id 101
        self._write_meta(tmp, "project_a", {"project_id": 101, "name": "project_a"})

        # project_b with project_id 102
        self._write_meta(tmp, "project_b", {"project_id": 102, "name": "project_b"})

        # no_meta: directory without .evoloop/project.json
        os.makedirs(os.path.join(tmp, "no_meta"))

        yield tmp

        shutil.rmtree(tmp, ignore_errors=True)

    def _write_meta(self, root: str, dir_name: str, data: dict) -> None:
        meta_dir = os.path.join(root, dir_name, ".evoloop")
        os.makedirs(meta_dir, exist_ok=True)
        with open(os.path.join(meta_dir, "project.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_get_path_finds_existing_projects(self, workspace):
        index = LocalProjectIndex()

        assert index.get_path(101, workspace) == os.path.join(workspace, "project_a")
        assert index.get_path(102, workspace) == os.path.join(workspace, "project_b")

    def test_get_path_returns_none_for_unknown_project(self, workspace):
        index = LocalProjectIndex()

        assert index.get_path(999, workspace) is None

    def test_get_project_id_by_path(self, workspace):
        index = LocalProjectIndex()

        assert index.get_project_id(os.path.join(workspace, "project_a"), workspace) == 101
        assert index.get_project_id(os.path.join(workspace, "project_b"), workspace) == 102
        assert index.get_project_id(os.path.join(workspace, "no_meta"), workspace) is None

    def test_conflict_logs_warning_but_keeps_first_discovered(self, caplog):
        tmp = tempfile.mkdtemp(prefix="test_conflict_workspace_")
        try:
            # Use directory names that sort deterministically by creation order is
            # still filesystem-dependent, so we only assert behavior invariants:
            # - exactly one of the two directories wins
            # - a warning is emitted
            # - neither file is mutated
            self._write_meta(tmp, "first", {"project_id": 101, "name": "first"})
            self._write_meta(tmp, "second", {"project_id": 101, "name": "second"})

            index = LocalProjectIndex()
            result = index.get_path(101, tmp)
            assert result in {
                os.path.join(tmp, "first"),
                os.path.join(tmp, "second"),
            }
            assert any("project_id 101 conflict" in rec.message for rec in caplog.records)

            for name in ("first", "second"):
                meta_file = os.path.join(tmp, name, ".evoloop", "project.json")
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)
                assert meta.get("project_id") == 101
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_workspace_returns_none(self):
        index = LocalProjectIndex()

        assert index.get_path(101, "/nonexistent/path") is None

    def test_invalid_json_is_ignored(self, workspace):
        meta_dir = os.path.join(workspace, "invalid_json", ".evoloop")
        os.makedirs(meta_dir, exist_ok=True)
        with open(os.path.join(meta_dir, "project.json"), "w", encoding="utf-8") as f:
            f.write("not json")

        index = LocalProjectIndex()
        assert index.get_path(101, workspace) == os.path.join(workspace, "project_a")

    def test_invalid_project_id_type_is_ignored(self, workspace):
        self._write_meta(workspace, "bad_id", {"project_id": "not-an-int"})

        index = LocalProjectIndex()
        assert index.get_path(101, workspace) == os.path.join(workspace, "project_a")

    def test_refresh_rebuilds_index_after_changes(self, workspace):
        index = LocalProjectIndex()

        assert index.get_path(101, workspace) is not None

        # Remove project_a meta
        shutil.rmtree(os.path.join(workspace, "project_a", ".evoloop"))

        assert index.get_path(101, workspace) is None

    def test_empty_workspace(self):
        tmp = tempfile.mkdtemp(prefix="empty_workspace_")
        try:
            index = LocalProjectIndex()
            assert index.refresh(tmp) == {}
            assert index.get_path(1, tmp) is None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
