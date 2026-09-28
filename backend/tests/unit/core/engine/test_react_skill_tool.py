"""React `skill` tool entry tests — registration + not-found + permission gate wiring."""

from app.core.tools.registry import get_agent_tools, get_tool_map


def test_skill_tool_is_registered_and_in_react_face():
    from app.core.tools.registry import _invalidate_caches

    _invalidate_caches()
    assert "skill" in get_tool_map()
    names = {t.name for t in get_agent_tools("react")}
    assert "skill" in names


def test_skill_tool_not_benefit_gated_by_default():
    """skill 权限走授权门控（TOOL_PERMISSIONS），不依赖 required_benefit（会员权益）。"""
    from app.core.config import settings
    from app.core.tools.registry import _invalidate_caches, get_tool_map

    assert not hasattr(settings, "SKILL_REQUIRED_BENEFIT")
    _invalidate_caches()
    assert "skill" in get_tool_map()


def test_skill_tool_returns_not_found_without_guess(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    from app.core.engine.tools.react_skill import skill

    monkeypatch.setattr(
        "app.core.engine.react.skills.manager.skill_discovery.exact_search",
        AsyncMock(return_value=(None, [], "no match")),
    )

    async def _run():
        return await skill(name="__definitely_not_a_skill__")

    out = asyncio.run(_run())
    assert "not found" in out or "不要猜名" in out


def test_skill_tool_list_action_enumerates_all_skills(monkeypatch):
    """action="list"：索引被裁/截断时的兜底发现路径，枚举全部活跃技能。"""
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.core.engine.tools.react_skill import skill

    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_active_skills_list",
        AsyncMock(
            return_value=[
                SimpleNamespace(id=1, name="Agent Reach", namespace="agentreach",
                                description="互联网能力路由器"),
                SimpleNamespace(id=2, name="deep_research", namespace="general",
                                description="深度调研"),
            ]
        ),
    )

    async def _run():
        return await skill(action="list")

    out = asyncio.run(_run())
    assert "Agent Reach: 互联网能力路由器" in out
    assert "deep_research: 深度调研" in out
    assert 'skill(action="load"' in out


def test_skill_tool_load_without_name_points_to_list():
    """load 缺 name → 指引先 list，不静默猜名。"""
    import asyncio

    from app.core.engine.tools.react_skill import skill

    async def _run():
        return await skill()

    out = asyncio.run(_run())
    assert 'action="list"' in out


def test_skill_tool_schema_action_is_enum_and_name_optional():
    """wire schema 契约：action 为 enum 且默认 load；name 非必填（向后兼容 skill(name=...)）。"""
    from app.core.engine.sdk_adapter.tools import _schema_from_signature
    from app.core.engine.tools import react_skill

    schema = _schema_from_signature(react_skill.skill.func)
    action = schema["properties"]["action"]
    assert action["type"] == "string"
    assert set(action["enum"]) == {"load", "list"}
    assert "name" in schema["properties"]
    assert "name" not in schema.get("required", [])
