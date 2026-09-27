"""自动识别 + 保险 验收测试（2026-09-18 用户确认方案）。

链路：skill 激活包 → 反哺 session_domain → 下一轮按域装配收窄 →
已用工具保底保留（混合会话安全阀）。

锁定语义：
1. hint 域（host_declared/classified）优先级高于包反哺；
2. 已执行过的工具在收窄面之上保底保留，面只单调变化；
3. 未用过的工具随域面收窄消失（场景 A/B 验收见 test_assembly_scenarios.py）；
4. 被钩子拦截的工具不计入保底（记录发生在 PRE_TOOL_USE 放行之后）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.context.schemas import ContextMetadata
from app.core.engine.state import AgentState

MALL_FACE = {"webfetch", "websearch", "plan", "skill", "question", "tasks"}


def _native_tool(name: str):
    t = MagicMock()
    t.name = name
    t.metadata = {}
    return t


def _mall_project(tmp_path):
    home = tmp_path / "mall-backend"
    (home / ".evoloop").mkdir(parents=True)
    (home / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n  mall_ops:\n    native_tools: [webfetch, websearch, plan, skill, question, tasks]\n",
        encoding="utf-8",
    )
    return home


def _setup(monkeypatch, tmp_path, metadata: ContextMetadata):
    from app.core.engine.capability_profiles import reload as reload_profiles
    from app.core.tools.manager import tool_manager

    reload_profiles(str(tmp_path))
    ctx = MagicMock()
    ctx.metadata = metadata
    ctx.working_directory = str(tmp_path)
    monkeypatch.setattr(
        "app.core.context.ContextManager.current", staticmethod(lambda: ctx)
    )
    import app.core.tools.registry as registry_mod

    monkeypatch.setattr(
        registry_mod,
        "get_agent_tools",
        lambda agent: [_native_tool(n) for n in
                       {"bash", "read", "glob", "grep", "edit", "write", "task",
                        "webfetch", "websearch", "plan", "tasks", "skill",
                        "question", "browser", "image", "video", "mobile",
                        "desktop", "vault", "macro"}],
    )
    monkeypatch.setattr(
        "app.infrastructure.config.service.SystemConfigService",
        MagicMock(get_value=staticmethod(lambda k: "vision-model")),
    )
    return tool_manager, ctx


@pytest.mark.asyncio
async def test_package_feedback_narrows_surface_next_turn(tmp_path, monkeypatch):
    """激活 mall 包（无 hint 域）→ session_domain 反哺 → 下轮收窄到域面。"""
    from app.core.engine.capability_profiles import reload as reload_profiles
    from app.core.engine.tools.react_skill import _activate_package_capability

    home = _mall_project(tmp_path)
    session = tmp_path / "session"
    session.mkdir()
    reload_profiles(str(session))

    tool_manager, ctx = _setup(monkeypatch, session, ContextMetadata())
    monkeypatch.setattr(
        "app.core.mcp.mcp_client_manager.ensure_connected",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    resource_path=str(home / ".evoloop" / "skills" / "mall-products")
                )
            ]
        ),
    )

    # 轮 1：激活包 → 记账 + 反哺
    await _activate_package_capability(
        {
            "name": "mall-products",
            "content": "# SOP",
            "base_dir": "/x",
            "files": [],
            "capability": {
                "domain": "mall_ops",
                "tools": [{"mcp_server": "mall-backend-ops", "include": ["list_goods"]}],
            },
        }
    )
    assert ctx.metadata.session_domain == "mall_ops"
    assert ctx.metadata.loaded_packages == ["mall-products"]

    # 轮 2：无 hint，反哺域生效 → 收窄
    tools = await tool_manager.get_agent_tools("react", state=AgentState())
    assert {t.name for t in tools} == MALL_FACE


@pytest.mark.asyncio
async def test_used_tools_floor_keeps_session_tools(tmp_path, monkeypatch):
    """保险：会话用过的 bash/mobile 在域面收窄后保底保留。"""
    home = _mall_project(tmp_path)
    session = tmp_path / "session"
    session.mkdir()

    metadata = ContextMetadata(
        session_domain="mall_ops",
        used_native_tools=["bash", "mobile"],
    )
    tool_manager, _ = _setup(monkeypatch, session, metadata)
    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    resource_path=str(home / ".evoloop" / "skills" / "mall-products")
                )
            ]
        ),
    )

    tools = await tool_manager.get_agent_tools("react", state=AgentState())
    names = {t.name for t in tools}
    assert names == MALL_FACE | {"bash", "mobile"}


@pytest.mark.asyncio
async def test_hint_domain_overrides_package_feedback(tmp_path, monkeypatch):
    """优先级：hint 域（host_declared/classified）> 包反哺 session_domain。"""
    from app.core.engine.capability_profiles import reload as reload_profiles

    other = tmp_path / "game-backend"
    (other / ".evoloop").mkdir(parents=True)
    (other / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n  game_ops:\n    native_tools: [bash, read]\n",
        encoding="utf-8",
    )
    session = tmp_path / "session"
    session.mkdir()
    reload_profiles(str(session))

    metadata = ContextMetadata(
        session_domain="mall_ops",
        intent_hint=SimpleNamespace(domain="game_ops"),
    )
    tool_manager, _ = _setup(monkeypatch, session, metadata)
    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    resource_path=str(other / ".evoloop" / "skills" / "game-pkg")
                )
            ]
        ),
    )

    tools = await tool_manager.get_agent_tools("react", state=AgentState())
    assert {t.name for t in tools} == {"bash", "read"}


@pytest.mark.asyncio
async def test_unresolvable_hint_domain_does_not_block_feedback(tmp_path, monkeypatch):
    """hint 域（如分类器标签 'ecommerce'）不可装配时，不得阻塞可装配的
    包反哺域 'mall_ops'（2026-09-18 实测教训：两套域词汇表冲突场景）。"""
    home = _mall_project(tmp_path)
    session = tmp_path / "session"
    session.mkdir()

    metadata = ContextMetadata(
        session_domain="mall_ops",
        intent_hint=SimpleNamespace(domain="ecommerce"),  # 分类器标签：无 profile 无包
    )
    tool_manager, _ = _setup(monkeypatch, session, metadata)

    async def fake_get_packages_for_domain(domain):
        # 'ecommerce' 域目录为空（词汇表不一致）；mall_ops 有包
        return (
            [SimpleNamespace(resource_path=str(home / ".evoloop" / "skills" / "mall-products"))]
            if domain == "mall_ops"
            else []
        )

    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
        AsyncMock(side_effect=fake_get_packages_for_domain),
    )

    tools = await tool_manager.get_agent_tools("react", state=AgentState())
    names = {t.name for t in tools}
    assert names == MALL_FACE  # 反哺域生效，未被 hint 阻塞


def test_record_used_tool_dedup_and_cap():
    """记账：去重 + 上限；被拦截的工具由调用侧保证不传入。"""
    from app.core.engine.tools.executor import (
        USED_NATIVE_TOOLS_CAP,
        record_used_native_tool,
    )

    metadata = ContextMetadata()
    record_used_native_tool(metadata, "bash")
    record_used_native_tool(metadata, "bash")
    record_used_native_tool(metadata, "read")
    assert metadata.used_native_tools == ["bash", "read"]

    metadata2 = ContextMetadata(
        used_native_tools=[f"t{i}" for i in range(USED_NATIVE_TOOLS_CAP)]
    )
    record_used_native_tool(metadata2, "new-tool")
    assert "new-tool" not in metadata2.used_native_tools  # 封顶后不再记
