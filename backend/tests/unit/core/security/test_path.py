"""Unit tests for app.core.security.path."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.core.security.path import (
    _normalize_path,
    command_touches_project_metadata,
    extract_command_paths,
    get_allowed_roots,
    is_path_safe,
    is_project_metadata_path,
)


class TestIsProjectMetadataPath:
    def test_app_data_file_is_not_metadata(self, monkeypatch, tmp_path):
        app_data = tmp_path / ".evoloop"
        app_data.mkdir()
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(app_data)
        )
        assert is_project_metadata_path(str(app_data / "backend.db")) is False

    def test_relative_evoloop_is_metadata(self, monkeypatch, tmp_path):
        app_data = tmp_path / ".evoloop"
        app_data.mkdir()
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(app_data)
        )
        assert is_project_metadata_path(".evoloop/project.json") is True

    def test_project_local_evoloop_is_metadata(self, monkeypatch, tmp_path):
        app_data = tmp_path / ".evoloop"
        app_data.mkdir()
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(app_data)
        )
        assert (
            is_project_metadata_path("/Users/foo/project/.evoloop/project.json") is True
        )

    def test_non_evoloop_path_is_not_metadata(self):
        assert is_project_metadata_path("/tmp/foo.txt") is False


class TestGetAllowedRoots:
    def test_includes_working_dir_app_data_and_workspace_root(
        self, tmp_path, monkeypatch
    ):
        wd = tmp_path / "wd"
        wd.mkdir()
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(evoloop)
        )
        with patch(
            "app.core.security.path.get_workspace_root", return_value=str(workspace)
        ):
            roots = get_allowed_roots(working_dir=str(wd))

        abs_roots = {os.path.abspath(r) for r in roots}
        assert os.path.abspath(str(wd)) in abs_roots
        assert os.path.abspath(str(evoloop)) in abs_roots
        assert os.path.abspath(str(workspace)) in abs_roots

    def test_skips_nonexistent_directories(self, tmp_path, monkeypatch):
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(evoloop)
        )
        with patch(
            "app.core.security.path.get_workspace_root", return_value="/does/not/exist"
        ):
            roots = get_allowed_roots()
        assert os.path.abspath(str(evoloop)) in {os.path.abspath(r) for r in roots}
        assert "/does/not/exist" not in roots

    def test_project_scope_excludes_workspace_root(self, tmp_path, monkeypatch):
        """项目会话激活：WORKSPACE_ROOT / ALLOWED_PATH_PREFIXES 不再整体放行。

        安全修复（2026-09-15）：project_path 非空时边界收敛为
        working_dir + project_path + ~/.evoloop，跨项目访问走 authorized_paths。
        """
        wd = tmp_path / "proj"
        wd.mkdir()
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        prefix = tmp_path / "prefix"
        prefix.mkdir()

        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(evoloop)
        )
        monkeypatch.setattr(
            "app.core.config.settings.ALLOWED_PATH_PREFIXES", [str(prefix)]
        )
        with patch(
            "app.core.security.path.get_workspace_root", return_value=str(workspace)
        ):
            roots = get_allowed_roots(
                working_dir=str(wd), project_path=str(wd)
            )

        abs_roots = {os.path.abspath(r) for r in roots}
        assert os.path.abspath(str(wd)) in abs_roots
        assert os.path.abspath(str(evoloop)) in abs_roots
        assert os.path.abspath(str(workspace)) not in abs_roots
        assert os.path.abspath(str(prefix)) not in abs_roots

    def test_global_mode_still_includes_workspace_root(self, tmp_path, monkeypatch):
        """全局模式（无 project_path）：宿主运维语义不变（回归保护）。"""
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(evoloop)
        )
        with patch(
            "app.core.security.path.get_workspace_root", return_value=str(workspace)
        ):
            roots = get_allowed_roots()

        abs_roots = {os.path.abspath(r) for r in roots}
        assert os.path.abspath(str(workspace)) in abs_roots


class TestIsPathSafe:
    def test_relative_path_against_working_dir(self, tmp_path, monkeypatch):
        wd = tmp_path / "project"
        wd.mkdir()
        file = wd / "data.json"
        file.write_text("{}")
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(tmp_path / ".evoloop")
        )
        assert is_path_safe("data.json", working_dir=str(wd)) is True

    def test_absolute_path_outside_all_roots_blocked(self, tmp_path, monkeypatch):
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(evoloop)
        )
        monkeypatch.setattr("app.core.config.settings.ALLOWED_PATH_PREFIXES", [])
        with patch("app.core.security.path.get_workspace_root", return_value=""):
            assert is_path_safe("/tmp/secret.txt") is False

    def test_empty_path_is_not_safe(self):
        assert is_path_safe("") is False

    def test_project_scope_blocks_workspace_sibling(self, tmp_path, monkeypatch):
        """本次事故场景回归：WORKSPACE_ROOT 下的兄弟项目目录必须判为不安全。

        项目 A 激活时，读取同一 WORKSPACE_ROOT 下项目 B 的内容（如 备份/、
        其他项目 data/）属于跨项目访问，不得因 WORKSPACE_ROOT 白名单放行。
        """
        project = tmp_path / "workspace" / "project-a"
        project.mkdir(parents=True)
        sibling = tmp_path / "workspace" / "project-b" / "secrets"
        sibling.mkdir(parents=True)
        evoloop = tmp_path / ".evoloop"
        evoloop.mkdir()

        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(evoloop)
        )
        monkeypatch.setattr(
            "app.core.config.settings.ALLOWED_PATH_PREFIXES", []
        )
        with patch(
            "app.core.security.path.get_workspace_root",
            return_value=str(tmp_path / "workspace"),
        ):
            assert is_path_safe(
                str(sibling), working_dir=str(project), project_path=str(project)
            ) is False
            # 项目内路径仍然安全
            inside = project / "data.json"
            inside.write_text("{}")
            assert is_path_safe(
                str(inside), working_dir=str(project), project_path=str(project)
            ) is True


class TestExtractCommandPaths:
    """execute_command 命令文本路径提取（缺陷 SECURITY_execute_command_path_bypass）。"""

    def test_absolute_path_argument(self):
        assert extract_command_paths(
            "grep -rln addGoods /Users/u/Projects/develop-assistant.cn --include=*.py"
        ) == [("/Users/u/Projects/develop-assistant.cn", "read")]

    def test_piped_absolute_path(self):
        assert extract_command_paths(
            "ls -la /Users/u/www/mall-backend 2>&1 | head -50"
        ) == [("/Users/u/www/mall-backend", "read")]

    def test_relative_path_resolved_against_base_dir(self):
        assert extract_command_paths(
            "cat relative/data.json", base_dir="/base/wd"
        ) == [("/base/wd/relative/data.json", "read")]

    def test_relative_path_skipped_without_base_dir(self):
        assert extract_command_paths("cat relative/data.json") == []

    def test_redirect_target_is_write(self):
        assert extract_command_paths("echo hi > /outside/f") == [
            ("/outside/f", "write")
        ]
        assert extract_command_paths("echo hi >> /outside/f") == [
            ("/outside/f", "write")
        ]
        assert extract_command_paths("echo hi >/outside/f") == [
            ("/outside/f", "write")
        ]

    def test_absolute_binary_command_word_skipped(self):
        """绝对路径二进制作为命令字（如 php 解释器）不算越界路径参数。"""
        assert (
            extract_command_paths(
                "/usr/local/opt/php@8.1/bin/php think goods:publish"
            )
            == []
        )

    def test_sudo_and_env_prelude(self):
        # rm 是写动词：路径参数按 write 门控（审批卡如实显示写/删语义）
        assert extract_command_paths("sudo rm -rf /outside/x") == [
            ("/outside/x", "write")
        ]
        assert extract_command_paths("env FOO=bar mv a.txt b.txt") == []

    def test_write_verbs_classified_as_write(self):
        """写动词（rm/cp/mkdir/tee/sed -i）的路径参数按 write 门控，
        普通读命令保持 read。修复前 rm 被标成 read（审批语义倒挂）。"""
        assert extract_command_paths("rm /outside/x") == [("/outside/x", "write")]
        assert extract_command_paths("mkdir -p /outside/a/b") == [
            ("/outside/a/b", "write")
        ]
        assert extract_command_paths("tee /outside/f") == [("/outside/f", "write")]
        assert extract_command_paths("cp /outside/a /outside/b") == [
            ("/outside/a", "write"),
            ("/outside/b", "write"),
        ]
        assert extract_command_paths("sed -i 's/a/b/' /outside/f") == [
            ("/outside/f", "write")
        ]
        # 普通 sed 是读
        assert extract_command_paths("sed 's/a/b/' /outside/f") == [
            ("/outside/f", "read")
        ]
        # 同一路径先读后写：去重取更严格的 write（不得丢失写语义）
        assert extract_command_paths("cat /outside/f && rm /outside/f") == [
            ("/outside/f", "write")
        ]
        # 同一路径先写后读：write 不得被降级回 read
        assert extract_command_paths("rm /outside/f && cat /outside/f") == [
            ("/outside/f", "write")
        ]
        # 管道分段各自判定：读段保持 read
        assert extract_command_paths("cat /outside/a | grep x") == [
            ("/outside/a", "read")
        ]

    def test_write_verb_flag_values_and_dd(self):
        """写动词分段里的操作数值（dd if= of=、tee -a、sed -i.bak）按 write 门控。"""
        assert extract_command_paths("dd if=/outside/a of=/outside/b") == [
            ("/outside/a", "write"),
            ("/outside/b", "write"),
        ]
        assert extract_command_paths("tee -a /outside/f") == [("/outside/f", "write")]
        assert extract_command_paths("sed -i.bak 's/a/b/' /outside/f") == [
            ("/outside/f", "write")
        ]
        # env 赋值（动词前）不参与检查——保持既有语义
        assert extract_command_paths("env FOO=bar cat /outside/f") == [
            ("/outside/f", "read")
        ]

    def test_quoted_path_with_space(self):
        assert extract_command_paths('cat "/path with space/f"') == [
            ("/path with space/f", "read")
        ]

    def test_flag_value_extraction(self):
        assert extract_command_paths("tool --output=/outside/x --verbose") == [
            ("/outside/x", "read")
        ]
        assert extract_command_paths("tool -o /outside/x") == [("/outside/x", "read")]

    def test_double_dash_stops_flag_parsing(self):
        assert extract_command_paths("rm -- /outside/odd-name") == [
            ("/outside/odd-name", "write")
        ]

    def test_chained_segments(self):
        assert extract_command_paths("cd /outside && cat /outside2/f") == [
            ("/outside", "read"),
            ("/outside2/f", "read"),
        ]

    def test_deduplicated(self):
        assert extract_command_paths("grep -rn foo /a /a") == [("/a", "read")]

    def test_home_relative_path_expanded(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert extract_command_paths("cat ~/outside/f") == [
            (str(tmp_path / "outside" / "f"), "read")
        ]

    def test_no_paths_returns_empty(self):
        assert extract_command_paths("git status") == []
        assert extract_command_paths("ls") == []

    def test_unbalanced_quotes_safe(self):
        assert extract_command_paths("echo 'unclosed") == []

    def test_empty_command(self):
        assert extract_command_paths("") == []
        assert extract_command_paths("   ") == []


class TestNormalizePath:
    def test_normalizes_symlinks_and_user_home(self, tmp_path, monkeypatch):
        # Ensure expanduser does not break in tests by monkeypatching HOME.
        monkeypatch.setenv("HOME", str(tmp_path))
        assert _normalize_path("~/foo").startswith(str(tmp_path))

    def test_falls_back_on_oserror(self):
        with patch("os.path.realpath", side_effect=OSError("boom")):
            result = _normalize_path("/some/path")
        assert result == os.path.abspath("/some/path")


class TestCommandTouchesProjectMetadata:
    def test_workspace_absolute_path_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(tmp_path / ".evoloop")
        )
        assert (
            command_touches_project_metadata(
                "cat /Users/foo/proj/.evoloop/project.json"
            )
            is True
        )

    def test_relative_path_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(tmp_path / ".evoloop")
        )
        assert command_touches_project_metadata("ls .evoloop") is True

    def test_upper_case_evoloop_blocked(self, tmp_path, monkeypatch):
        """命令 token 大小写不敏感（与 is_project_metadata_path 一致）。"""
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(tmp_path / ".evoloop")
        )
        assert command_touches_project_metadata("cat /PROJ/.EVOLOOP/x.json") is True

    def test_trailing_shell_metacharacters_blocked(self, tmp_path, monkeypatch):
        """token 尾部 shell 元字符应被剥除，仍命中。"""
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(tmp_path / ".evoloop")
        )
        assert (
            command_touches_project_metadata("cat /proj/.evoloop/x.json; echo done")
            is True
        )

    def test_home_relative_project_blocked(self, tmp_path, monkeypatch):
        """~/proj/.evoloop 属项目元数据，拦截。"""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(tmp_path / ".evoloop")
        )
        assert command_touches_project_metadata("cat ~/proj/.evoloop/x.json") is True

    def test_app_data_exempt(self, tmp_path, monkeypatch):
        """全局应用数据目录 ~/.evoloop 下的引用豁免。"""
        app_data = tmp_path / ".evoloop"
        app_data.mkdir()
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(
            "app.core.config.settings.EVOLOOP_APP_DATA_DIR", str(app_data)
        )
        assert (
            command_touches_project_metadata("cat ~/.evoloop/skills/foo/SKILL.md")
            is False
        )

    def test_bare_word_not_blocked(self):
        """纯含 .evoloop 子串的普通词（非路径）不拦截。"""
        assert command_touches_project_metadata("echo foo.evoloop.bar") is False

    def test_unrelated_command_not_blocked(self):
        assert command_touches_project_metadata("ls -la /tmp/proj/src") is False

    def test_empty_command_not_blocked(self):
        assert command_touches_project_metadata("") is False
