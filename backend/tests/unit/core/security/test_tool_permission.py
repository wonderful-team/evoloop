"""Tool-level permission gate tests (OpenCode Permission ruleset equivalent).

`TOOL_PERMISSIONS = {tool: "allow"|"ask"|"deny"}` 驱动 AuthorizationEvaluator
返回工具级决策；"ask" 时已批准 grant 自动放行（对齐 OpenCode approved rules）。
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.security.authorization import AuthorizationEvaluator
from app.core.security.policy_loader import GrantedPermission


def _eval(monkeypatch, rules: dict, granted: list | None = None):
    monkeypatch.setattr(settings, "TOOL_PERMISSIONS", rules)
    ev = AuthorizationEvaluator(project_id=None)
    ev._policies = []
    ev._granted = granted or []
    return ev


@pytest.mark.asyncio
async def test_absent_tool_falls_through_to_resource(monkeypatch):
    # 不在 TOOL_PERMISSIONS 内 → 走资源级；skill 无资源 → 默认放行
    ev = _eval(monkeypatch, {})
    d = await ev.evaluate("skill", None)
    assert d.approved is True
    assert d.requires_hitl is False


@pytest.mark.asyncio
async def test_tool_deny_blocks(monkeypatch):
    ev = _eval(monkeypatch, {"skill": "deny"})
    d = await ev.evaluate("skill", None)
    assert d.approved is False
    assert d.requires_hitl is False
    assert d.resource_path == "skill"


@pytest.mark.asyncio
async def test_tool_ask_escalates_to_hitl(monkeypatch):
    ev = _eval(monkeypatch, {"skill": "ask"})
    d = await ev.evaluate("skill", None)
    assert d.approved is False
    assert d.requires_hitl is True
    assert d.policy is not None
    assert d.resource_path == "skill"
    assert d.action == "invoke"


@pytest.mark.asyncio
async def test_tool_ask_with_grant_auto_approves(monkeypatch):
    grant = GrantedPermission(
        path="skill",
        action="invoke",
        approved_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    ev = _eval(monkeypatch, {"skill": "ask"}, granted=[grant])
    d = await ev.evaluate("skill", None)
    assert d.approved is True
    assert d.requires_hitl is False


@pytest.mark.asyncio
async def test_tool_allow(monkeypatch):
    ev = _eval(monkeypatch, {"task": "allow"})
    d = await ev.evaluate("task", None)
    assert d.approved is True
    assert d.requires_hitl is False


@pytest.mark.asyncio
async def test_tool_permission_does_not_override_resource_rules(monkeypatch):
    # TOOL_PERMISSIONS 只影响列出的工具；bash 走原资源级
    ev = _eval(monkeypatch, {"skill": "deny"})
    d = await ev.evaluate("bash", None)
    # bash 无 command → _extract_resource 返回 None → 放行
    assert d.approved is True


def test_permanent_grant_never_expires():
    """allow always：expires_at=None 永不过期。"""
    grant = GrantedPermission(
        path="skill",
        action="invoke",
        approved_at=datetime.now(timezone.utc),
        expires_at=None,
    )
    assert grant.is_expired(now=datetime.now(timezone.utc) + timedelta(days=3650)) is False


def test_ttl_grant_expires():
    grant = GrantedPermission(
        path="skill",
        action="invoke",
        approved_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert grant.is_expired() is True


def test_permanent_grant_serialization_roundtrip():
    """expires_at=None 序列化（json 存 None）后仍可还原为永久授权。"""
    grant = GrantedPermission(
        path="skill",
        action="invoke",
        approved_at=datetime.now(timezone.utc),
        expires_at=None,
    )
    restored = GrantedPermission.from_dict(grant.to_dict())
    assert restored.expires_at is None
    assert restored.is_expired() is False
    assert "expires_at" in grant.to_dict() and grant.to_dict()["expires_at"] is None
