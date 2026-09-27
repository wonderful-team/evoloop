"""Unit tests for the unified file-change diff (``app.core.file.changes.diff``)."""

import pytest

from app.core.file.changes.diff import compute_file_diff


class TestComputeFileDiff:
    def test_edit_operation_and_diff(self):
        result = compute_file_diff("hello\nworld\n", "hello\npython\n", "f.txt")
        assert result.operation == "EDIT"
        assert result.original == "hello\nworld\n"
        assert "a/f.txt" in result.diff
        assert "-world" in result.diff
        assert "+python" in result.diff

    def test_add_operation(self):
        result = compute_file_diff("", "new content\n", "f.txt")
        assert result.operation == "ADD"
        assert result.original is None

    def test_delete_operation(self):
        result = compute_file_diff("gone\ncontent\n", "", "f.txt")
        assert result.operation == "DELETE"
        assert result.original == "gone\ncontent\n"

    def test_no_change_returns_empty(self):
        result = compute_file_diff("same\n", "same\n", "f.txt")
        assert result.operation == ""
        assert result.diff == ""
        assert result.original is None

    def test_last_line_without_newline_is_fixed(self):
        """末行无换行：diff 头必须正确（不因缺 \n 而丢行/错位）。"""
        result = compute_file_diff("a\nb", "a\nc", "f.txt")
        assert result.operation == "EDIT"
        assert "-b" in result.diff
        assert "+c" in result.diff

    def test_add_first_line_diff_headers(self):
        result = compute_file_diff("", "x\n", "f.txt")
        assert result.diff.startswith("--- a/f.txt")
        assert "+++ b/f.txt" in result.diff

    def test_context_lines_default_is_3(self):
        """默认 context_lines=3（与 generate_unified_diff 对齐）。"""
        result = compute_file_diff("1\n2\n3\n4\n5\n6\n7\n8\n9\n", "1\n2\n3\n4\nX\n6\n7\n8\n9\n", "f.txt")
        # 变更行前后各 3 行上下文 → 共 1 + 6 = 7 行内容在 hunk 内
        assert "+X" in result.diff

    def test_frozen_dataclass(self):
        import dataclasses

        result = compute_file_diff("a\n", "b\n", "f.txt")
        assert dataclasses.is_dataclass(result)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.operation = "ADD"
