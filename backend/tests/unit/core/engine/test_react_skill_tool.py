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
