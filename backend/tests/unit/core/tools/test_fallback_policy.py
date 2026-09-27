"""ToolManager fallback minimal-core 策略与跨项目 profile 回退接线测试（2026-09-18）。"""

from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.engine.state import AgentState


def _native_tool(name: str):
    t = MagicMock()
    t.name = name
    t.metadata = {}
    return t


@pytest.mark.asyncio
async def test_fallback_policy_narrows_native_surface(tmp_path, monkeypatch):
    """项目声明 fallback.native_tools + 无域信号 → 原生面收窄到白名单。"""
    from app.core.context.schemas import ContextMetadata
    from app.core.tools.manager import tool_manager

    (tmp_path / ".evoloop").mkdir()
    (tmp_path / ".evoloop" / "capability_profiles.yaml").write_text(
        textwrap.dedent(
            """\
            domains: {}
            fallback:
              native_tools: [bash, read]
            """
        ),
        encoding="utf-8",
    )
    from app.core.engine.capability_profiles import reload as reload_profiles

    reload_profiles(str(tmp_path))

    ctx = MagicMock()
    ctx.metadata = ContextMetadata()
    ctx.working_directory = str(tmp_path)
    monkeypatch.setattr(
        "app.core.context.ContextManager.current", staticmethod(lambda: ctx)
    )
    monkeypatch.setattr(
        type(tool_manager), "_resolve_domain_profile", staticmethod(lambda: None)
    )
    # registry 静态面
    import app.core.tools.registry as registry_mod

    monkeypatch.setattr(
        registry_mod,
        "get_agent_tools",
        lambda agent: [
            _native_tool("bash"),
            _native_tool("read"),
            _native_tool("desktop"),
        ],
    )
    monkeypatch.setattr(
        "app.infrastructure.config.service.SystemConfigService",
        MagicMock(get_value=staticmethod(lambda k: "vision-model")),
    )

    tools = await tool_manager.get_agent_tools("react", state=AgentState())
    assert {t.name for t in tools} == {"bash", "read"}


@pytest.mark.asyncio
async def test_no_fallback_policy_keeps_full_surface(tmp_path, monkeypatch):
    """未声明 fallback → 全量现状（零回归锁）。"""
    from app.core.context.schemas import ContextMetadata
    from app.core.engine.capability_profiles import reload as reload_profiles
    from app.core.tools.manager import tool_manager

    reload_profiles(str(tmp_path))

    ctx = MagicMock()
    ctx.metadata = ContextMetadata()
    ctx.working_directory = str(tmp_path)
    monkeypatch.setattr(
        "app.core.context.ContextManager.current", staticmethod(lambda: ctx)
    )
    monkeypatch.setattr(
        type(tool_manager), "_resolve_domain_profile", staticmethod(lambda: None)
    )
    import app.core.tools.registry as registry_mod

    monkeypatch.setattr(
        registry_mod,
        "get_agent_tools",
        lambda agent: [_native_tool("bash"), _native_tool("desktop")],
    )
    monkeypatch.setattr(
        "app.infrastructure.config.service.SystemConfigService",
        MagicMock(get_value=staticmethod(lambda k: "vision-model")),
    )

    tools = await tool_manager.get_agent_tools("react", state=AgentState())
    assert {t.name for t in tools} == {"bash", "desktop"}


@pytest.mark.asyncio
async def test_hint_domain_resolves_profile_from_package_home(tmp_path, monkeypatch):
    """hint 域在会话工作区无 profile → 经包源项目回退命中（manager 接线）。"""
    from app.core.context.schemas import ContextMetadata
    from app.core.tools.manager import tool_manager

    home = tmp_path / "mall-backend"
    (home / ".evoloop").mkdir(parents=True)
    (home / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n  mall_ops:\n    native_tools: [skill, question]\n",
        encoding="utf-8",
    )
    session_wd = tmp_path / "session"
    session_wd.mkdir()
    from app.core.engine.capability_profiles import reload as reload_profiles

    reload_profiles(str(session_wd))

    hint = MagicMock()
    hint.domain = "mall_ops"
    ctx = MagicMock()
    ctx.metadata = ContextMetadata(intent_hint=hint)
    ctx.working_directory = str(session_wd)
    monkeypatch.setattr(
        "app.core.context.ContextManager.current", staticmethod(lambda: ctx)
    )
    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
        AsyncMock(
            return_value=[
                MagicMock(
                    resource_path=str(home / ".evoloop" / "skills" / "mall-products")
                )
            ]
        ),
    )
    import app.core.tools.registry as registry_mod

    monkeypatch.setattr(
        registry_mod,
        "get_agent_tools",
        lambda agent: [
            _native_tool("bash"),
            _native_tool("skill"),
            _native_tool("question"),
        ],
    )
    monkeypatch.setattr(
        "app.infrastructure.config.service.SystemConfigService",
        MagicMock(get_value=staticmethod(lambda k: "vision-model")),
    )

    tools = await tool_manager.get_agent_tools("react", state=AgentState())
    assert {t.name for t in tools} == {"skill", "question"}
