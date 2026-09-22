"""Unit tests for authorization hook helpers."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.core.context.thread_store import thread_context_store
from app.core.engine.hooks.authorization import authorization_gate
from app.core.engine.hooks.core import HookContext
from app.core.engine.hooks.schemas import ToolInput
from app.core.hitl.core import hitl_enabled
from app.core.security.authorization import (
    AuthorizationDecision,
    AuthorizationPolicy,
)


@pytest.fixture
def app_data_dir(monkeypatch, tmp_path):
    """Point ``~/.evoloop`` to a temp directory for the duration of the test."""
    app_data = tmp_path / ".evoloop"
    app_data.mkdir()
    monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(app_data))
    return str(app_data)


class TestToolInputTouchesProjectMetadata:
    """ToolInput.touches_project_metadata：收集并裁决结构化字段与命令文本。"""

    def test_app_data_file_allowed(self, app_data_dir):
        tool_input = ToolInput(path=os.path.join(app_data_dir, "backend.db"))
        assert tool_input.touches_project_metadata() is False

    def test_app_data_directory_allowed(self, app_data_dir):
        tool_input = ToolInput(path=app_data_dir)
        assert tool_input.touches_project_metadata() is False

    def test_app_data_with_tilde_allowed(self, app_data_dir, monkeypatch):
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", "~/.evoloop")
        tool_input = ToolInput(path="~/.evoloop/skills/foo/SKILL.md")
        assert tool_input.touches_project_metadata() is False

    def test_relative_evoloop_blocked(self, app_data_dir):
        tool_input = ToolInput(path=".evoloop/project.json")
        assert tool_input.touches_project_metadata() is True

    def test_project_local_evoloop_blocked(self, app_data_dir):
        tool_input = ToolInput(path="/Users/foo/project/.evoloop/project.json")
        assert tool_input.touches_project_metadata() is True

    def test_upper_case_evoloop_blocked(self, app_data_dir):
        """大小写不敏感：path 字段 /PROJ/.EVOLOOP 同样拦截。"""
        tool_input = ToolInput(path="/PROJ/.EVOLOOP/project.json")
        assert tool_input.touches_project_metadata() is True

    def test_args_app_data_allowed(self, app_data_dir):
        tool_input = ToolInput(args={"AbsolutePath": os.path.join(app_data_dir, "x")})
        assert tool_input.touches_project_metadata() is False

    def test_args_project_local_blocked(self, app_data_dir):
        tool_input = ToolInput(args={"AbsolutePath": "/Users/foo/project/.evoloop/x"})
        assert tool_input.touches_project_metadata() is True

    def test_command_project_evoloop_blocked(self, app_data_dir):
        """execute_command 里引用工作区 .evoloop → 拦截（防 shell 触碰项目元数据）。"""
        tool_input = ToolInput(
            command="echo x >> /Users/foo/project/.evoloop/project.json"
        )
        assert tool_input.touches_project_metadata() is True

    def test_command_project_evoloop_read_blocked(self, app_data_dir):
        tool_input = ToolInput(command="cat /proj/.evoloop/project.json; echo done")
        assert tool_input.touches_project_metadata() is True

    def test_command_upper_case_evoloop_blocked(self, app_data_dir):
        """命令 token 大小写不敏感（与 is_project_metadata_path 一致）。"""
        tool_input = ToolInput(command="cat /PROJ/.EVOLOOP/project.json")
        assert tool_input.touches_project_metadata() is True

    def test_command_global_app_data_allowed(self, app_data_dir):
        """全局 APP_DATA_DIR 下的 .evoloop 路径，命令行引用不拦截。"""
        tool_input = ToolInput(command=f"cat {app_data_dir}/skills/foo.md")
        assert tool_input.touches_project_metadata() is False

    def test_command_unrelated_allowed(self, app_data_dir):
        tool_input = ToolInput(command="ls -la /tmp/proj/src")
        assert tool_input.touches_project_metadata() is False

    def test_command_bare_word_allowed(self, app_data_dir):
        """纯含 .evoloop 子串的普通词不算路径，不误拦。"""
        tool_input = ToolInput(command="echo foo.evoloop.bar")
        assert tool_input.touches_project_metadata() is False


class TestAuthorizationGateI18n:
    @pytest.mark.asyncio
    async def test_metadata_violation_message_is_localized(self):
        """触碰项目 .evoloop 元数据时的拦截文案应走 i18n。"""
        ctx = HookContext(
            thread_id="t-1",
            run_id="r-1",
            project_id=120,
            tool_name="read_file",
            tool_input=ToolInput(path="/proj/.evoloop/backend.db"),
            tool_use_id="call-1",
        )
        with patch(
            "app.i18n.service.SystemConfigService.get_value",
            return_value="zh",
        ):
            result = await authorization_gate(ctx)
        assert result.block is True
        assert "安全违规" in result.message
        assert ".evoloop" in result.message

    @pytest.mark.asyncio
    async def test_metadata_violation_message_is_localized_en(self):
        """英文环境下返回英文拦截文案。"""
        ctx = HookContext(
            thread_id="t-2",
            run_id="r-1",
            project_id=120,
            tool_name="read_file",
            tool_input=ToolInput(path="/proj/.evoloop/backend.db"),
            tool_use_id="call-2",
        )
        with patch(
            "app.i18n.service.SystemConfigService.get_value",
            return_value="en",
        ):
            result = await authorization_gate(ctx)
        assert result.block is True
        assert "SECURITY VIOLATION" in result.message
        assert ".evoloop" in result.message


class TestGlobalModeMetadataGate:
    """全局模式（无项目）下 .evoloop 元数据仍应被拦截，~/.evoloop 应用数据豁免。

    回归：authorization_gate 原先在 project_id 为空时提前放行，导致全局模式下
    execute_command 命令文本里的 .evoloop 引用无人拦截（LocalSandbox 无 OS 隔离）。
    修复后元数据硬拦截先于全局早退执行。
    """

    def _ctx(
        self,
        project_id: int | None,
        tool_name: str,
        tool_input: ToolInput,
    ) -> HookContext:
        return HookContext(
            thread_id="t-global",
            run_id="r-1",
            project_id=project_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_use_id="call-g",
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("project_id", [None, 0])
    async def test_global_mode_blocks_workspace_evoloop(self, project_id, app_data_dir):
        ctx = self._ctx(
            project_id,
            "read_file",
            ToolInput(path="/Users/foo/proj/.evoloop/project.json"),
        )
        with patch(
            "app.i18n.service.SystemConfigService.get_value",
            return_value="zh",
        ):
            result = await authorization_gate(ctx)
        assert result.block is True
        assert "安全违规" in result.message

    @pytest.mark.asyncio
    @pytest.mark.parametrize("project_id", [None, 0])
    async def test_global_mode_blocks_execute_command_evoloop(
        self, project_id, app_data_dir
    ):
        """全局模式 shell 引用工作区 .evoloop 同样拦截（原缺口主场景）。"""
        ctx = self._ctx(
            project_id,
            "execute_command",
            ToolInput(command="cat /Users/foo/proj/.evoloop/project.json"),
        )
        with patch(
            "app.i18n.service.SystemConfigService.get_value",
            return_value="zh",
        ):
            result = await authorization_gate(ctx)
        assert result.block is True
        assert "安全违规" in result.message

    @pytest.mark.asyncio
    @pytest.mark.parametrize("project_id", [None, 0])
    async def test_global_mode_allows_app_data(self, project_id, app_data_dir):
        """全局 ~/.evoloop 应用数据豁免仍然成立（元数据检查通过后直接放行）。"""
        ctx = self._ctx(
            project_id,
            "read_file",
            ToolInput(path=os.path.join(app_data_dir, "skills", "foo", "SKILL.md")),
        )
        result = await authorization_gate(ctx)
        assert result.success is True
        assert result.block is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("project_id", [None, 0])
    async def test_global_mode_allows_app_data_command(self, project_id, app_data_dir):
        ctx = self._ctx(
            project_id,
            "execute_command",
            ToolInput(command=f"cat {app_data_dir}/skills/foo/SKILL.md"),
        )
        result = await authorization_gate(ctx)
        assert result.success is True
        assert result.block is False


class TestAuthorizationGateCommandPaths:
    """execute_command 命令文本路径越界 → 与文件工具同走 HITL 授权。

    缺陷回归：SECURITY_execute_command_path_bypass + 2026-09-15 跨项目翻找
    事故（capability_matrix 项目 Agent 用 grep 挖 develop-assistant.cn 全工作区）。
    组合验证两项修复：
    1. get_allowed_roots 项目作用域（WORKSPACE_ROOT 不再整体放行）；
    2. authorization_gate 对命令文本提取路径参数并套用同一边界。
    """

    def _make_ctx(self, command: str, thread_id: str = "t-cmd") -> HookContext:
        return HookContext(
            thread_id=thread_id,
            run_id="r-1",
            project_id=42,
            tool_name="execute_command",
            tool_input=ToolInput(command=command),
            tool_use_id="call-cmd",
        )

    @pytest.fixture
    def project_env(self, tmp_path, monkeypatch):
        """项目 A 激活，同 WORKSPACE_ROOT 下有兄弟项目 B。"""
        project = tmp_path / "workspace" / "project-a"
        project.mkdir(parents=True)
        sibling_secret = tmp_path / "workspace" / "project-b" / "secrets.txt"
        sibling_secret.parent.mkdir(parents=True)
        sibling_secret.write_text("root/admin888")
        app_data = tmp_path / ".evoloop"
        app_data.mkdir()

        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(app_data))
        monkeypatch.setattr(settings, "EXECUTION_MODE", "local")
        monkeypatch.setattr(settings, "ALLOWED_PATH_PREFIXES", [])
        monkeypatch.setattr(
            "app.core.security.path.get_workspace_root",
            lambda: str(tmp_path / "workspace"),
        )
        return project, sibling_secret

    def _patch_common(self, project):
        return (
            patch(
                "app.core.engine.hooks.authorization.AuthorizationService",
            ),
            patch(
                "app.core.engine.hooks.authorization.get_project_path",
                AsyncMock(return_value=str(project)),
            ),
            patch.object(
                thread_context_store,
                "get_working_directory",
                return_value=str(project),
            ),
        )

    @pytest.mark.asyncio
    async def test_command_outside_project_escalates_hitl(
        self, project_env, monkeypatch
    ):
        """事故主场景：grep 命令引用同工作区兄弟项目路径 → HITL 审批。"""
        project, sibling_secret = project_env
        ctx = self._make_ctx(
            f"grep -rln password {sibling_secret} --include=*.py"
        )
        service = _StubAuthService()
        p1, p2, p3 = self._patch_common(project)
        with p1 as mock_cls, p2, p3:
            mock_cls.return_value = service
            await authorization_gate(ctx)

        service.request_authorization.assert_awaited_once()
        kwargs = service.request_authorization.await_args.kwargs
        assert kwargs["decision"].requires_hitl is True
        assert kwargs["decision"].resource_path == str(sibling_secret)
        assert kwargs["decision"].action == "read"

    @pytest.mark.asyncio
    async def test_command_inside_project_allowed(self, project_env):
        """项目内路径命令不升级（既有工作流零回归）。"""
        project, _ = project_env
        inside = project / "data.json"
        inside.write_text("{}")
        ctx = self._make_ctx(f"cat {inside} && ls {project}")
        service = _StubAuthService()
        p1, p2, p3 = self._patch_common(project)
        with p1 as mock_cls, p2, p3:
            mock_cls.return_value = service
            result = await authorization_gate(ctx)

        assert result.success is True
        assert result.block is False
        service.request_authorization.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_command_redirect_outside_escalates_write(self, project_env):
        """重定向写越界 → action=write 的 HITL 审批。"""
        project, sibling_secret = project_env
        target = sibling_secret.parent / "escaped.txt"
        ctx = self._make_ctx(f"echo hi > {target}")
        service = _StubAuthService()
        p1, p2, p3 = self._patch_common(project)
        with p1 as mock_cls, p2, p3:
            mock_cls.return_value = service
            await authorization_gate(ctx)

        service.request_authorization.assert_awaited_once()
        kwargs = service.request_authorization.await_args.kwargs
        assert kwargs["decision"].action == "write"
        assert kwargs["decision"].resource_path == str(target)

    @pytest.mark.asyncio
    async def test_command_outside_with_granted_permission_allowed(
        self, project_env
    ):
        """authorized_paths 已授权（read + 匹配路径）→ 命令访问放行。"""
        project, sibling_secret = project_env
        grant = SimpleNamespace(
            action="read",
            path=str(sibling_secret),
            is_expired=lambda now: False,
        )
        ctx = self._make_ctx(f"cat {sibling_secret}")
        service = _StubAuthService()
        service._granted = [grant]
        p1, p2, p3 = self._patch_common(project)
        with p1 as mock_cls, p2, p3:
            mock_cls.return_value = service
            result = await authorization_gate(ctx)

        assert result.success is True
        assert result.block is False
        service.request_authorization.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_duty_thread_command_outside_still_hitl(self, project_env):
        """值守线程命令越界同样走 HITL（不静默、不 auto-reject）。"""
        project, sibling_secret = project_env
        ctx = self._make_ctx(
            f"ls -la {sibling_secret.parent}", thread_id="duty_42_kf1"
        )
        service = _StubAuthService()
        p1, p2, p3 = self._patch_common(project)
        with p1 as mock_cls, p2, p3:
            mock_cls.return_value = service
            await authorization_gate(ctx)

        service.request_authorization.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_previously_rejected_resource_hard_blocked(
        self, project_env, monkeypatch
    ):
        """拒绝即判死：同线程同资源已被拒绝过 → 直接 block，不再新建审批。"""
        project, sibling_secret = project_env
        ctx = self._make_ctx(f"cat {sibling_secret}")
        service = _StubAuthService()
        p1, p2, p3 = self._patch_common(project)
        with (
            p1 as mock_cls,
            p2,
            p3,
            patch(
                "app.core.engine.hooks.authorization.HITLOrchestrator.has_thread_resource_rejection",
                AsyncMock(return_value=True),
            ),
        ):
            mock_cls.return_value = service
            result = await authorization_gate(ctx)

        assert result.block is True
        assert "已拒绝" in (result.message or "")
        service.request_authorization.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_compound_command_single_approval_covers_all_paths(
        self, project_env
    ):
        """复合命令多路径 → 一次审批覆盖全部越界路径（extra_paths 全量授权）。

        回归背景：修复前 gate 在首个越界路径 break，审批只授权单路径；批准后
        重执行在下一个未授权路径再次弹审批，一条 4 路径命令连环弹 4 次审批。
        """
        project, _ = project_env
        path_a = project.parent / "outside-a.txt"
        path_b = project.parent / "outside-b.txt"
        ctx = self._make_ctx(f"ls {path_a}; ls {path_b}")
        service = _StubAuthService()
        p1, p2, p3 = self._patch_common(project)
        with p1 as mock_cls, p2, p3:
            mock_cls.return_value = service
            await authorization_gate(ctx)

        service.request_authorization.assert_awaited_once()
        kwargs = service.request_authorization.await_args.kwargs
        assert kwargs["decision"].resource_path == str(path_a)
        extra = kwargs["extra_paths"]
        # 单一事实源：extra_paths 含全部越界路径（含首路径），resolve 只认这份列表
        assert (str(path_a), "read") in extra
        assert (str(path_b), "read") in extra

    @pytest.mark.asyncio
    async def test_write_verb_command_escalates_write_action(self, project_env):
        """rm 越界 → action=write（修复前误标 read，审批卡显示"读取"）。"""
        project, _ = project_env
        target = project.parent / "doomed.txt"
        ctx = self._make_ctx(f"rm -f {target}")
        service = _StubAuthService()
        p1, p2, p3 = self._patch_common(project)
        with p1 as mock_cls, p2, p3:
            mock_cls.return_value = service
            await authorization_gate(ctx)

        service.request_authorization.assert_awaited_once()
        kwargs = service.request_authorization.await_args.kwargs
        assert kwargs["decision"].action == "write"
        assert kwargs["decision"].resource_path == str(target)

    @pytest.mark.asyncio
    async def test_reexec_approval_allows_once(self, project_env):
        """DB 认领放行：同一 tool_call 在窗口内被批准（双轨 COMPLETED+APPROVED）
        → 门控放行重执行；无批准记录 → 正常发起审批。"""
        from app.core.hitl.orchestrator import HITLOrchestrator

        project, sibling_secret = project_env
        ctx = self._make_ctx(f"cat {sibling_secret}", thread_id="t-reexec")
        service = _StubAuthService()

        async def _approved(thread_id, tool_call_id, window_seconds=None):
            return tool_call_id == "call-cmd"

        p1, p2, p3 = self._patch_common(project)
        with (
            p1 as mock_cls,
            p2,
            p3,
            patch.object(
                HITLOrchestrator,
                "was_call_recently_approved",
                new=AsyncMock(side_effect=_approved),
            ),
        ):
            mock_cls.return_value = service
            result = await authorization_gate(ctx)

        assert result.success is True
        assert result.block is False
        service.request_authorization.assert_not_awaited()

        # 无近期批准记录（其他 call_id）→ 照常发起审批
        ctx2 = self._make_ctx(f"cat {sibling_secret}", thread_id="t-reexec")
        ctx2.tool_use_id = "call-other"
        service2 = _StubAuthService()
        with (
            p1 as mock_cls,
            p2,
            p3,
            patch.object(
                HITLOrchestrator,
                "was_call_recently_approved",
                new=AsyncMock(return_value=False),
            ),
        ):
            mock_cls.return_value = service2
            await authorization_gate(ctx2)
        service2.request_authorization.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_docker_mode_command_outside_auto_approved(
        self, project_env, monkeypatch
    ):
        """docker 模式：命令越界免 HITL（沙箱隔离兜底，不发起审批）。"""
        project, sibling_secret = project_env
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        assert not hitl_enabled()

        ctx = self._make_ctx(f"cat {sibling_secret}")
        service = _StubAuthService()
        p1, p2, p3 = self._patch_common(project)
        with p1 as mock_cls, p2, p3:
            mock_cls.return_value = service
            result = await authorization_gate(ctx)

        assert result.success is True
        assert result.block is False
        service.request_authorization.assert_not_awaited()


class _StubAuthService:
    def __init__(self, approved_decision: AuthorizationDecision | None = None):
        self._granted = []
        self.evaluate = AsyncMock(
            return_value=approved_decision
            or AuthorizationDecision(
                approved=True,
                requires_hitl=False,
                reason="no policy match",
                resource_path="/opt/evoloop-outside/secrets.txt",
                action="write",
            )
        )
        self.request_authorization = AsyncMock()
        self._load = AsyncMock()


class TestAuthorizationGateExecutionMode:
    """EXECUTION_MODE=docker 时工作区外路径免 HITL（沙箱隔离兜底）。"""

    OUT_PATH = "/opt/evoloop-outside/secrets.txt"

    def _make_ctx(self, tool_name="write_file", path=OUT_PATH) -> HookContext:
        return HookContext(
            thread_id="t-hitl",
            run_id="r-1",
            project_id=42,
            tool_name=tool_name,
            tool_input=ToolInput(path=path),
            tool_use_id="call-x",
        )

    @pytest.mark.asyncio
    async def test_docker_mode_skips_hitl_for_outside_workspace(
        self, tmp_path, monkeypatch
    ):
        """docker 模式：工作区外写路径直接放行，不发起授权审批。"""
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        assert not hitl_enabled()

        ctx = self._make_ctx()
        service = _StubAuthService()
        with (
            patch(
                "app.core.engine.hooks.authorization.AuthorizationService",
                return_value=service,
            ),
            patch(
                "app.core.engine.hooks.authorization.get_project_path",
                AsyncMock(return_value=str(tmp_path / "proj")),
            ),
            patch.object(
                thread_context_store,
                "get_working_directory",
                return_value=str(tmp_path),
            ),
        ):
            result = await authorization_gate(ctx)

        assert result.success is True
        assert result.block is False
        service.request_authorization.assert_not_awaited()
        service.request_authorization.assert_not_called()

    @pytest.mark.asyncio
    async def test_local_mode_requests_hitl_for_outside_workspace(
        self, tmp_path, monkeypatch
    ):
        """local 模式：工作区外写路径仍走 HITL 授权审批。"""
        monkeypatch.setattr(settings, "EXECUTION_MODE", "local")
        assert hitl_enabled()

        ctx = self._make_ctx()
        service = _StubAuthService()
        with (
            patch(
                "app.core.engine.hooks.authorization.AuthorizationService",
                return_value=service,
            ),
            patch(
                "app.core.engine.hooks.authorization.get_project_path",
                AsyncMock(return_value=str(tmp_path / "proj")),
            ),
            patch.object(
                thread_context_store,
                "get_working_directory",
                return_value=str(tmp_path),
            ),
        ):
            await authorization_gate(ctx)

        service.request_authorization.assert_awaited_once()
        request_kwargs = service.request_authorization.await_args.kwargs
        assert request_kwargs["tool_name"] == "write_file"
        assert request_kwargs["decision"].requires_hitl is True
        assert request_kwargs["decision"].resource_path == self.OUT_PATH

    @pytest.mark.asyncio
    async def test_docker_mode_still_blocks_project_metadata(self, monkeypatch):
        """docker 模式：项目 .evoloop 元数据仍无条件拦截（不豁免）。"""
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")

        ctx = HookContext(
            thread_id="t-3",
            run_id="r-1",
            project_id=42,
            tool_name="write_file",
            tool_input=ToolInput(path="/Users/foo/proj/.evoloop/project.json"),
            tool_use_id="call-3",
        )
        with patch(
            "app.i18n.service.SystemConfigService.get_value",
            return_value="zh",
        ):
            result = await authorization_gate(ctx)
        assert result.block is True
        assert "安全违规" in result.message

    @pytest.mark.asyncio
    async def test_docker_mode_auto_approves_project_policy_hitl(
        self, tmp_path, monkeypatch
    ):
        """docker 模式：project.json 策略判定 requires_hitl 也自动批准（不发起审批）。

        路径位于工作区内（安全），故走纯策略分支而非 Safety-Boundary。
        """
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        workdir = str(tmp_path)
        sensitive = str(tmp_path / "secrets.txt")

        ctx = HookContext(
            thread_id="t-4",
            run_id="r-1",
            project_id=42,
            tool_name="read_file",
            tool_input=ToolInput(path=sensitive),
            tool_use_id="call-4",
        )
        policy_hitl = AuthorizationDecision(
            approved=False,
            requires_hitl=True,
            reason="project policy requires approval",
            policy=AuthorizationPolicy(
                resource_type="file",
                action="read",
                patterns=[sensitive],
                requires_approval=True,
                risk_level="high",
            ),
            resource_path=sensitive,
            action="read",
        )
        service = _StubAuthService(approved_decision=policy_hitl)
        with (
            patch(
                "app.core.engine.hooks.authorization.AuthorizationService",
                return_value=service,
            ),
            patch(
                "app.core.engine.hooks.authorization.get_project_path",
                AsyncMock(return_value=workdir),
            ),
            patch.object(
                thread_context_store,
                "get_working_directory",
                return_value=workdir,
            ),
        ):
            result = await authorization_gate(ctx)

        assert result.success is True
        assert result.block is False
        service.request_authorization.assert_not_awaited()
