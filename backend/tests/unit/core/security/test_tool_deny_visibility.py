"""Tool-level deny visibility + authorization rejection feedback tests.

- 被 TOOL_PERMISSIONS deny 的工具应从 react 工具面移除（visibleTools 语义）。
- 授权拒绝（ask-reject）返回 CorrectedError 风格消息，让模型自纠、不重试。
"""


from app.core.config import settings
from app.core.tools.registry import _invalidate_caches, get_agent_tools


def _reset_cache():
    _invalidate_caches()


def test_deny_tool_removed_from_react_face(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_PERMISSIONS", {"webfetch": "deny"})
    _reset_cache()
    names = {t.name for t in get_agent_tools("react")}
    assert "webfetch" not in names
    assert "bash" in names  # 未 deny 的工具保留


def test_allow_tool_kept_in_react_face(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_PERMISSIONS", {"webfetch": "allow"})
    _reset_cache()
    names = {t.name for t in get_agent_tools("react")}
    assert "webfetch" in names


def test_ask_tool_not_hidden_from_react_face(monkeypatch):
    # ask 只是调用时走 HITL，不隐藏工具（对齐 OpenCode：ask ≠ 不可见）
    monkeypatch.setattr(settings, "TOOL_PERMISSIONS", {"webfetch": "ask"})
    _reset_cache()
    names = {t.name for t in get_agent_tools("react")}
    assert "webfetch" in names


async def test_authorization_reject_returns_corrected_style_message():
    from app.core.hitl.orchestrator import HITLOrchestrator

    pending_tool = {
        "name": "bash",
        "id": "c1",
        "args": {"command": "rm -rf /x"},
        "authorization": {"resource_path": "rm -rf /x", "action": "execute"},
    }
    out = await HITLOrchestrator.resolve_approved_tool_result(
        pending_tool=pending_tool,
        config={},
        fallback_result="REJECTED",
    )
    assert "REJECTED" in out
    assert "bash" in out
    assert "不要重试" in out or "未执行" in out


async def test_authorization_deny_message_includes_tool_and_reason(monkeypatch):
    from app.core.security.authorization import AuthorizationEvaluator

    monkeypatch.setattr(settings, "TOOL_PERMISSIONS", {"skill": "deny"})
    ev = AuthorizationEvaluator(project_id=None)
    ev._policies = []
    ev._granted = []
    decision = await ev.evaluate("skill", None)
    assert decision.approved is False
    assert decision.requires_hitl is False
    assert "denied" in decision.reason.lower() or "拒绝" in decision.reason
