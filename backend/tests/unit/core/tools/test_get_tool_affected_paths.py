"""Unit tests for ``get_tool_affected_paths`` 泛化后的行为。

- 工具声明 ``affected_path_keys`` → 从结构化参数提取路径（file 中心工具）
- 工具声明 ``affected_path_extractor`` → 用工具自身的解析器（execute_command）
- 不再有按工具名的 execute_command 特判（删除后行为不变，且扩展了 mv/cp/sed/echo）
"""

from app.core.tools.registry import get_tool_affected_paths


class TestMetadataKeys:
    def test_file_edit_affected_path_keys(self):
        assert get_tool_affected_paths(
            "file", {"action": "edit", "path": "/abs/x.py"}
        ) == ["/abs/x.py"]

    def test_file_edit_ignores_other_keys(self):
        assert get_tool_affected_paths("file", {"action": "edit", "target": "/other.py"}) == []

    def test_file_write_affected_path_keys(self):
        assert get_tool_affected_paths("file", {"action": "write", "path": "x.py"}) == ["x.py"]

    def test_file_move_both_source_and_dest(self):
        assert get_tool_affected_paths(
            "file", {"action": "move", "source": "a", "destination": "b"}
        ) == [
            "a",
            "b",
        ]


class TestCommandExtractor:
    def test_rm(self):
        assert get_tool_affected_paths("bash", {"command": "rm -rf /tmp/x"}) == ["/tmp/x"]

    def test_mv(self):
        assert get_tool_affected_paths("bash", {"command": "mv a.txt b.txt"}) == [
            "a.txt",
            "b.txt",
        ]

    def test_sed(self):
        assert get_tool_affected_paths("bash", {"command": "sed -i 's/x/y/' f.txt"}) == ["f.txt"]

    def test_echo_redirect(self):
        assert get_tool_affected_paths("bash", {"command": "echo hi > out.txt"}) == ["out.txt"]

    def test_read_only_command_returns_empty(self):
        assert get_tool_affected_paths("bash", {"command": "ls -la"}) == []


class TestGenericFallback:
    def test_state_mutating_fallback_path_key(self):
        """通用回退：mutating 工具参数含 path/file_path/TargetFile 时兜底。"""
        from app.core.tools.registry import is_state_mutating_tool

        assert is_state_mutating_tool("file")
        assert get_tool_affected_paths("file", {"action": "write", "path": "gen.py"}) == [
            "gen.py"
        ]
