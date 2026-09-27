"""Unit tests for ``execute_command`` 的 shell 路径提取启发式。

覆盖 rm / mv / cp / sed -i / echo 重定向，以及 sudo 前缀、引号等边界。
"""


from app.core.execution.terminal.tools.execute import _parse_command_targets


class TestParseCommandTargets:
    def test_rm_simple(self):
        assert _parse_command_targets({"command": "rm file.txt"}) == ["file.txt"]

    def test_rm_with_flags(self):
        assert _parse_command_targets({"command": "rm -rf /tmp/x"}) == ["/tmp/x"]

    def test_rm_multiple_paths(self):
        assert _parse_command_targets({"command": "rm a.txt b.txt c.txt"}) == [
            "a.txt",
            "b.txt",
            "c.txt",
        ]

    def test_mv_source_and_dest(self):
        assert _parse_command_targets({"command": "mv src.txt dst.txt"}) == [
            "src.txt",
            "dst.txt",
        ]

    def test_cp_recursive(self):
        assert _parse_command_targets({"command": "cp -r dir1 dir2"}) == ["dir1", "dir2"]

    def test_sed_inplace(self):
        assert _parse_command_targets({"command": "sed -i 's/x/y/' f.txt"}) == ["f.txt"]

    def test_sed_inplace_with_backup_suffix(self):
        assert _parse_command_targets({"command": "sed -i.bak 's/x/y/' f.txt"}) == ["f.txt"]

    def test_sed_without_i_no_target(self):
        assert _parse_command_targets({"command": "sed 's/x/y/' f.txt"}) == []

    def test_echo_overwrite_redirect(self):
        assert _parse_command_targets({"command": "echo hi > out.txt"}) == ["out.txt"]

    def test_echo_append_redirect(self):
        assert _parse_command_targets({"command": "echo hi >> log.txt"}) == ["log.txt"]

    def test_quoted_redirect_target(self):
        assert _parse_command_targets({"command": 'echo hi > "my file.txt"'}) == ["my file.txt"]

    def test_sudo_prefix(self):
        assert _parse_command_targets({"command": "sudo rm -rf /tmp/x"}) == ["/tmp/x"]

    def test_sudo_with_flag_and_arg(self):
        """sudo -u user rm x：跳过 sudo 的 flag 及其参数，定位到 rm。"""
        assert _parse_command_targets({"command": "sudo -u deploy rm app.log"}) == [
            "app.log"
        ]

    def test_env_prefix_with_var(self):
        """env VAR=x mv a b：跳过环境变量，定位到 mv。"""
        assert _parse_command_targets({"command": "env FOO=bar mv a.txt b.txt"}) == [
            "a.txt",
            "b.txt",
        ]

    def test_multi_redirect_collects_all(self):
        assert _parse_command_targets({"command": "echo a > f1 > f2"}) == ["f1", "f2"]

    def test_mixed_redirect_and_append(self):
        assert _parse_command_targets({"command": "echo a > f1 >> f2"}) == ["f1", "f2"]

    def test_rm_double_dash(self):
        """rm -- file：-- 结束选项标记，其后路径仍应捕获。"""
        assert _parse_command_targets({"command": "rm -- odd-name.txt"}) == [
            "odd-name.txt"
        ]

    def test_background_command_skips_tracking(self):
        """background 命令异步执行，diff 时序不确定——明确不进 diff 追踪。"""
        assert _parse_command_targets(
            {"command": "rm -rf /tmp/x", "background": True}
        ) == []

    def test_background_false_still_tracks(self):
        assert _parse_command_targets(
            {"command": "rm -rf /tmp/x", "background": False}
        ) == ["/tmp/x"]

    def test_non_mutating_command(self):
        assert _parse_command_targets({"command": "ls -la"}) == []
        assert _parse_command_targets({"command": "git status"}) == []

    def test_empty_and_invalid(self):
        assert _parse_command_targets({}) == []
        assert _parse_command_targets({"command": ""}) == []
        assert _parse_command_targets({"command": "   "}) == []
        assert _parse_command_targets({"command": None}) == []

    def test_unbalanced_quotes_safe(self):
        # shlex 解析失败 → 安全返回空，不抛异常
        assert _parse_command_targets({"command": "rm 'unclosed"}) == []


def test_extractor_registered_on_tool():
    """affected_path_extractor 必须挂到已注册的 execute_command 工具上。"""
    from app.core.tools.registry import get_tool_map

    tool = get_tool_map().get("bash")
    assert tool is not None
    assert tool.affected_path_extractor is _parse_command_targets
