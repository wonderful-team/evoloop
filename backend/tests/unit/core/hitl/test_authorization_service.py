"""Tests for the project-level authorization framework.

Direct tests of ``AuthorizationService`` decision logic (no mocking of the
service itself): policy matching, approval requirements, granted-permission
reuse, path normalization, and HITL delegation.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.hitl.authorization import AuthorizationDecision, AuthorizationService
from app.core.hitl.policies import AuthorizationPolicy, GrantedPermission
from app.core.security.authorization import _extract_resource


@pytest.fixture(autouse=True)
def _force_en_locale():
    """Force English locale so string assertions are stable."""
    with patch(
        "app.i18n.service.SystemConfigService.get_value",
        return_value="en",
    ):
        yield


def _policy(**overrides) -> AuthorizationPolicy:
    base = {
        "resource_type": "file",
        "action": "read",
        "patterns": ["*.env", ".env.*"],
        "requires_approval": True,
        "risk_level": "high",
    }
    base.update(overrides)
    return AuthorizationPolicy(**base)


def _grant(path: str, action: str = "read", ttl_days: int = 7) -> GrantedPermission:
    now = datetime.now(timezone.utc)
    return GrantedPermission(
        path=path,
        action=action,
        approved_at=now,
        expires_at=now + timedelta(days=ttl_days),
    )


def _file_input(path: str | None, args: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(path=path, args=args if args is not None else {})


# ============ _extract_resource ============


def test_extract_resource_read_file_path_attr():
    assert _extract_resource(
        "file", _file_input("/data/x.env", args={"action": "read"})
    ) == (
        "/data/x.env",
        "read",
    )


def test_extract_resource_legacy_read_names_not_authorized():
    """收敛前旧工具名（read/view_file）不再映射——gate 只处理当前活工具。"""
    assert _extract_resource("read", _file_input("/data/x.env")) is None
    tool_input = SimpleNamespace(path=None, args={"path": "/data/x.env"})
    assert _extract_resource("view_file", tool_input) is None


def test_extract_resource_file_without_path_returns_none():
    assert _extract_resource("file", _file_input(None, args={"action": "read"})) is None


def test_extract_resource_write_tools():
    tool_input = SimpleNamespace(path=None, args={"action": "write", "path": "/data/x.env"})
    assert _extract_resource("file", tool_input) == ("/data/x.env", "write")


def test_extract_resource_legacy_engine_names_not_authorized():
    """旧引擎时代工具名不映射（OpenHands 引擎时代遗留名，ReAct 引擎无此工具）。"""
    tool_input = SimpleNamespace(path=None, args={"path": "/data/x.env"})
    for tool in ("replace_file_content", "multi_replace_file_content", "write_to_file"):
        assert _extract_resource(tool, tool_input) is None


def test_extract_resource_grep_search():
    tool_input = SimpleNamespace(path=None, args={"SearchPath": "/data"})
    assert _extract_resource("grep", tool_input) == ("/data", "read")


def test_extract_resource_execute_command_attr_and_args():
    tool_input = SimpleNamespace(command="rm -rf /", args={})
    assert _extract_resource("bash", tool_input) == ("rm -rf /", "execute")
    tool_input = SimpleNamespace(command=None, args={"command": "sudo ls"})
    assert _extract_resource("bash", tool_input) == ("sudo ls", "execute")


def test_extract_resource_none_input_and_unknown_tool():
    assert _extract_resource("read", None) is None
    assert _extract_resource("list_macros", _file_input("/x")) is None


# ============ evaluate ============


async def _evaluate(
    tool_name: str,
    tool_input,
    policies: list[AuthorizationPolicy] | None = None,
    grants: list[GrantedPermission] | None = None,
    project_path: str | None = "/proj",
) -> AuthorizationDecision:
    service = AuthorizationService(120)
    with (
        patch(
            "app.core.hitl.authorization.PolicyLoader.load_policies",
            AsyncMock(return_value=policies or []),
        ),
        patch(
            "app.core.hitl.authorization.PolicyLoader.load_granted_permissions",
            AsyncMock(return_value=grants or []),
        ),
        patch(
            "app.core.security.authorization.get_project_path",
            AsyncMock(return_value=project_path),
        ),
    ):
        return await service.evaluate(tool_name, tool_input)


@pytest.mark.asyncio
async def test_evaluate_unrelated_tool_always_approved():
    """非授权范围内的工具（无资源可提取）→ 直接放行。"""
    decision = await _evaluate("list_macros", SimpleNamespace(path="/x", args={}))
    assert decision.approved is True
    assert decision.requires_hitl is False


@pytest.mark.asyncio
async def test_evaluate_no_matching_policy_approved():
    """无匹配策略 → 放行（默认开放语义，仅敏感模式需要确认）。"""
    decision = await _evaluate("file", _file_input("/data/plain.txt", args={"action": "read"}), policies=[])
    assert decision.approved is True
    assert decision.requires_hitl is False


@pytest.mark.asyncio
async def test_evaluate_requires_approval_triggers_hitl():
    """匹配到 requires_approval 策略 → 需 HITL 确认。"""
    decision = await _evaluate(
        "file",
        _file_input("/proj/config/.env", args={"action": "read"}),
        policies=[_policy(patterns=["*.env"])],
    )
    assert decision.approved is False
    assert decision.requires_hitl is True
    assert "requires user approval" in decision.reason
    assert decision.policy is not None


@pytest.mark.asyncio
async def test_evaluate_policy_without_approval_passes():
    """匹配策略但 requires_approval=False → 放行。"""
    decision = await _evaluate(
        "file",
        _file_input("/proj/logs/app.log", args={"action": "read"}),
        policies=[_policy(patterns=["logs/*"], requires_approval=False)],
    )
    assert decision.approved is True
    assert decision.requires_hitl is False


@pytest.mark.asyncio
async def test_evaluate_wildcard_action_policy_matches():
    """action='*' 的策略匹配任意动作。"""
    decision = await _evaluate(
        "file",
        _file_input("/proj/keys/.env", args={"action": "read"}),
        policies=[_policy(action="*", patterns=["*.env"])],
    )
    assert decision.requires_hitl is True


@pytest.mark.asyncio
async def test_evaluate_action_mismatch_not_matched():
    """动作不匹配（write 策略 vs read 调用）→ 不命中，放行。"""
    decision = await _evaluate(
        "file",
        _file_input("/proj/keys/.env", args={"action": "read"}),
        policies=[_policy(action="write", patterns=["*.env"])],
    )
    assert decision.requires_hitl is False


@pytest.mark.asyncio
async def test_evaluate_valid_grant_bypasses_hitl():
    """有效期内已授权（path+action 精确匹配）→ 放行，无需再次确认。"""
    decision = await _evaluate(
        "file",
        _file_input("/proj/keys/.env", args={"action": "read"}),
        policies=[_policy(patterns=["*.env"])],
        grants=[_grant("keys/.env")],
        project_path="/proj",
    )
    assert decision.approved is True
    assert decision.requires_hitl is False
    assert decision.reason == "Previously authorized by user"


@pytest.mark.asyncio
async def test_evaluate_expired_grant_still_requires_hitl():
    """过期授权 → 仍需确认。"""
    decision = await _evaluate(
        "file",
        _file_input("/proj/keys/.env", args={"action": "read"}),
        policies=[_policy(patterns=["*.env"])],
        grants=[_grant("keys/.env", ttl_days=-1)],
        project_path="/proj",
    )
    assert decision.requires_hitl is True


@pytest.mark.asyncio
async def test_evaluate_normalizes_absolute_path_to_relative():
    """绝对路径归一化为项目相对路径后再匹配策略/授权。"""
    decision = await _evaluate(
        "file",
        _file_input("/proj/keys/.env", args={"action": "read"}),
        policies=[_policy(patterns=["keys/*"])],
        project_path="/proj",
    )
    assert decision.resource_path == "keys/.env"
    assert decision.requires_hitl is True


@pytest.mark.asyncio
async def test_evaluate_command_not_path_normalized():
    """execute 命令不参与路径归一化。"""
    decision = await _evaluate(
        "bash",
        SimpleNamespace(command="sudo ls", args={}),
        policies=[
            _policy(resource_type="command", action="execute", patterns=["sudo *"])
        ],
        project_path="/proj",
    )
    assert decision.resource_path == "sudo ls"
    assert decision.action == "execute"
    assert decision.requires_hitl is True


@pytest.mark.asyncio
async def test_evaluate_path_outside_project_not_relativized():
    """项目外的绝对路径（relpath 以 .. 开头）不归一化，保持绝对形态参与匹配。"""
    decision = await _evaluate(
        "file",
        _file_input("/etc/passwd", args={"action": "read"}),
        policies=[_policy(patterns=["passwd"])],
        project_path="/proj",
    )
    # 路径保持绝对形态（未被 relpath 掉）且命中 passwd 策略 → 需确认
    assert decision.resource_path == "/etc/passwd"
    assert decision.requires_hitl is True


@pytest.mark.asyncio
async def test_evaluate_get_project_path_failure_keeps_path():
    """get_project_path 失败 → 保持原路径继续评估。"""
    service = AuthorizationService(120)
    with (
        patch(
            "app.core.hitl.authorization.PolicyLoader.load_policies",
            AsyncMock(return_value=[_policy(patterns=["*.env"])]),
        ),
        patch(
            "app.core.hitl.authorization.PolicyLoader.load_granted_permissions",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.core.security.authorization.get_project_path",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
    ):
        decision = await service.evaluate("file", _file_input("/proj/keys/.env", args={"action": "read"}))
    # 路径未归一化，仍按绝对路径匹配 *.env 后缀 → 命中策略
    assert decision.requires_hitl is True


# ============ request_authorization / grant_permission ============


@pytest.mark.asyncio
async def test_request_authorization_without_policy_raises():
    """decision.policy 缺失 → ValueError（无策略不能发起授权请求）。"""
    service = AuthorizationService(120)
    decision = AuthorizationDecision(
        approved=False,
        requires_hitl=True,
        reason="no policy",
        resource_path="/x",
        action="read",
    )
    with pytest.raises(ValueError):
        await service.request_authorization("t-1", "file", "call-1", decision)


@pytest.mark.asyncio
async def test_request_authorization_delegates_to_orchestrator():
    """有策略 → 委托 HITLOrchestrator.request_authorization 并传正确参数。"""
    service = AuthorizationService(120)
    decision = AuthorizationDecision(
        approved=False,
        requires_hitl=True,
        reason="requires approval",
        policy=_policy(),
        resource_path="keys/.env",
        action="read",
    )
    with patch(
        "app.core.hitl.authorization.HITLOrchestrator.request_authorization",
        AsyncMock(),
    ) as mock_ra:
        await service.request_authorization(
            "t-1",
            "file",
            "call-1",
            decision,
            project_id=120,
            run_id="r-1",
            parent_id="m-1",
            original_tool_args={"path": "/proj/keys/.env"},
        )
    mock_ra.assert_awaited_once()
    kwargs = mock_ra.await_args.kwargs
    assert kwargs["action_description"] == "read keys/.env"
    assert kwargs["resource_path"] == "keys/.env"
    assert kwargs["risk_level"] == "high"
    assert kwargs["policy"] == decision.policy.to_dict()
    assert kwargs["original_tool_name"] == "file"
    assert kwargs["original_tool_args"] == {"path": "/proj/keys/.env"}


@pytest.mark.asyncio
async def test_grant_permission_without_project_id_returns_false():
    service = AuthorizationService(None)
    assert await service.grant_permission("/x", "read") is False


@pytest.mark.asyncio
async def test_grant_permission_persists_with_ttl():
    service = AuthorizationService(120)
    with patch(
        "app.core.hitl.authorization.PolicyLoader.save_granted_permission",
        AsyncMock(return_value=True),
    ) as mock_save:
        result = await service.grant_permission(
            "keys/.env", "read", granted_by="hitl-approval", ttl_days=3
        )
    assert result is True
    permission = mock_save.await_args.args[1]
    assert permission.path == "keys/.env"
    assert permission.action == "read"
    assert permission.granted_by == "hitl-approval"
    assert permission.expires_at - permission.approved_at == timedelta(days=3)


def test_extract_resource_write_without_path_returns_none():
    assert _extract_resource("write_to_file", _file_input(None)) is None


def test_extract_resource_grep_without_search_path_returns_none():
    tool_input = SimpleNamespace(path=None, args={})
    assert _extract_resource("grep", tool_input) is None


def test_extract_resource_command_without_command_returns_none():
    tool_input = SimpleNamespace(command=None, args={})
    assert _extract_resource("bash", tool_input) is None


@pytest.mark.asyncio
async def test_evaluate_loads_policies_once_and_caches():
    """_load 结果缓存：二次 evaluate 不再重查。"""
    service = AuthorizationService(120)
    with (
        patch(
            "app.core.hitl.authorization.PolicyLoader.load_policies",
            AsyncMock(return_value=[_policy(patterns=["*.env"])]),
        ) as mock_load,
        patch(
            "app.core.hitl.authorization.PolicyLoader.load_granted_permissions",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.core.security.authorization.get_project_path",
            AsyncMock(return_value="/proj"),
        ),
    ):
        await service.evaluate("file", _file_input("/proj/a.env", args={"action": "read"}))
        await service.evaluate("file", _file_input("/proj/b.env", args={"action": "read"}))
    assert mock_load.await_count == 1


@pytest.mark.asyncio
async def test_evaluate_without_project_id_uses_empty_policies():
    """无 project_id → 空策略/空授权（无项目则无门控）。"""
    service = AuthorizationService(None)
    decision = await service.evaluate("file", _file_input("/proj/a.env", args={"action": "read"}))
    assert decision.approved is True
    assert decision.requires_hitl is False


@pytest.mark.asyncio
async def test_evaluate_reason_is_i18n_aware():
    """Authorization reasons respect the configured locale."""
    with patch(
        "app.i18n.service.SystemConfigService.get_value",
        return_value="zh",
    ):
        decision = await _evaluate(
            "file",
            _file_input("/proj/config/.env", args={"action": "read"}),
            policies=[_policy(patterns=["*.env"])],
        )
    assert decision.approved is False
    assert decision.requires_hitl is True
    assert "需要用户审批" in decision.reason
    assert "config/.env" in decision.reason


@pytest.mark.asyncio
async def test_load_is_idempotent():
    service = AuthorizationService(project_id=120)
    with patch(
        "app.core.security.authorization.PolicyLoader.load_policies",
        AsyncMock(return_value=[]),
    ) as load_policies:
        await service._load()
        await service._load()
    load_policies.assert_awaited_once()


@pytest.mark.asyncio
async def test_is_granted_hit_permanent():
    """命中持久化授权（path+action 匹配且未过期）→ True。"""
    perm = GrantedPermission(
        path="macro:7",
        action="macro_run",
        approved_at=datetime.now(timezone.utc),
        expires_at=None,
    )
    with patch(
        "app.core.hitl.authorization.PolicyLoader.load_granted_permissions",
        new_callable=AsyncMock,
        return_value=[perm],
    ):
        assert await AuthorizationService(120).is_granted("macro:7", "macro_run") is True


@pytest.mark.asyncio
async def test_is_granted_mismatch():
    """路径/动作不匹配 → False。"""
    perm = GrantedPermission(
        path="macro:7",
        action="macro_run",
        approved_at=datetime.now(timezone.utc),
        expires_at=None,
    )
    with patch(
        "app.core.hitl.authorization.PolicyLoader.load_granted_permissions",
        new_callable=AsyncMock,
        return_value=[perm],
    ):
        service = AuthorizationService(120)
        assert await service.is_granted("macro:8", "macro_run") is False
        assert await service.is_granted("macro:7", "read") is False


@pytest.mark.asyncio
async def test_is_granted_expired_ttl_grant():
    """TTL grant 已过期 → False；永久 grant 永不过期 → True。"""
    base = {
        "path": "macro:7",
        "action": "macro_run",
        "approved_at": datetime.now(timezone.utc),
    }
    expired = GrantedPermission(
        path="macro:7",
        action="macro_run",
        approved_at=base["approved_at"],
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    with patch(
        "app.core.hitl.authorization.PolicyLoader.load_granted_permissions",
        new_callable=AsyncMock,
        return_value=[
            expired,
            GrantedPermission(
                path="macro:7",
                action="macro_run",
                approved_at=base["approved_at"],
                expires_at=None,
            ),
        ],
    ):
        assert await AuthorizationService(120).is_granted("macro:7", "macro_run") is True


@pytest.mark.asyncio
async def test_is_granted_missing_project_id():
    """project_id 缺失 → False（无授权域可查，不触存储）。"""
    with patch(
        "app.core.hitl.authorization.PolicyLoader.load_granted_permissions",
        new_callable=AsyncMock,
    ) as load:
        assert await AuthorizationService(None).is_granted("macro:7", "macro_run") is False
        load.assert_not_awaited()


@pytest.mark.asyncio
async def test_is_granted_prefix_scope_covers_children():
    """prefix 授权（grant_mode=dir）命中授权目录及全部子路径。"""
    perm = GrantedPermission(
        path="/outside/dir",
        action="read",
        scope_type="prefix",
        approved_at=datetime.now(timezone.utc),
        expires_at=None,
    )
    with patch(
        "app.core.hitl.authorization.PolicyLoader.load_granted_permissions",
        new_callable=AsyncMock,
        return_value=[perm],
    ):
        service = AuthorizationService(120)
        assert await service.is_granted("/outside/dir", "read") is True
        assert await service.is_granted("/outside/dir/sub/file.txt", "read") is True
        assert await service.is_granted("/outside/dir-sub/x", "read") is False


@pytest.mark.asyncio
async def test_is_granted_exact_scope_does_not_cover_children():
    """exact 授权不递归：子路径不命中（须逐路径授权，默认语义）。"""
    perm = GrantedPermission(
        path="/outside/dir",
        action="read",
        scope_type="exact",
        approved_at=datetime.now(timezone.utc),
        expires_at=None,
    )
    with patch(
        "app.core.hitl.authorization.PolicyLoader.load_granted_permissions",
        new_callable=AsyncMock,
        return_value=[perm],
    ):
        service = AuthorizationService(120)
        assert await service.is_granted("/outside/dir", "read") is True
        assert await service.is_granted("/outside/dir/child.txt", "read") is False


@pytest.mark.asyncio
async def test_is_granted_action_mismatch_not_covered():
    """read 授权不覆盖 write 访问（动作必须一致）。"""
    perm = GrantedPermission(
        path="/outside/dir",
        action="read",
        scope_type="prefix",
        approved_at=datetime.now(timezone.utc),
        expires_at=None,
    )
    with patch(
        "app.core.hitl.authorization.PolicyLoader.load_granted_permissions",
        new_callable=AsyncMock,
        return_value=[perm],
    ):
        assert (
            await AuthorizationService(120).is_granted("/outside/dir/child", "write")
            is False
        )


def test_granted_permission_scope_roundtrip_and_legacy_default():
    """scope_type 序列化往返；历史 project.json 记录（无该字段）默认 exact。"""
    now = datetime.now(timezone.utc)
    perm = GrantedPermission(
        path="/d",
        action="read",
        scope_type="prefix",
        approved_at=now,
        expires_at=None,
    )
    restored = GrantedPermission.from_dict(perm.to_dict())
    assert restored.scope_type == "prefix"

    legacy = GrantedPermission.from_dict(
        {
            "path": "/d",
            "action": "read",
            "approved_at": now.isoformat(),
            "expires_at": None,
        }
    )
    assert legacy.scope_type == "exact"
