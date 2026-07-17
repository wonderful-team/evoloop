"""Unit tests for P0.3a: move_file/delete_file use file center methods."""

import importlib.util
import re


def _get_source(module_name: str) -> str:
    spec = importlib.util.find_spec(module_name)
    assert spec is not None
    assert spec.origin is not None
    with open(spec.origin, "r") as f:
        return f.read()


class TestMoveFileUsesMovePath:
    def test_uses_move_path_not_shutil_move(self):
        src = _get_source("app.domain.tools.files.move_file")
        assert "move_path" in src
        assert "shutil.move" not in src

    def test_imports_from_app_core_file(self):
        src = _get_source("app.domain.tools.files.move_file")
        assert "from app.core.file import" in src or "from app.core.file" in src


class TestDeleteFileUsesFileCenter:
    def test_uses_core_delete_file_not_os_remove(self):
        src = _get_source("app.domain.tools.files.delete_file")
        assert "core_delete_file" in src
        assert "delete_directory" in src
        assert re.search(r'\bos\.remove\b', src) is None
        assert re.search(r'\bshutil\.rmtree\b', src) is None

    def test_imports_from_app_core_file(self):
        src = _get_source("app.domain.tools.files.delete_file")
        assert "from app.core.file import" in src or "from app.core.file" in src
