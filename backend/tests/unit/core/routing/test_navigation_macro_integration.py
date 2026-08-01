"""Integration tests for navigation macros backed by the DB macro system."""

import pytest

from app.core.execution.macro.runner import invalidate_macro_cache
from app.core.routing.command_router import CommandRouter
from app.core.routing.navigation_macro_cache import NavigationMacroCache
from app.infrastructure.database import session_scope
from app.models.macro import Macro
from app.utils.time import utcnow


def _make_nav_macro(phrase: str, route: str, feedback: str) -> Macro:
    return Macro(
        name=phrase,
        description=f"Navigate to {route}",
        trigger_patterns=[phrase],
        parameters=[],
        macro_script=f"""version: '1.0'
metadata:
  format: evoloop-macro
  step_count: 1
steps:
- type: action
  event_type: frontend_navigate
  source: desktop
  payload:
    route: {route}
""",
        risk_tier="observe",
        requires_confirmation=False,
        allow_self_healing=False,
        status="verified",
        is_active=True,
        namespace="preset",
        feedback=feedback,
        project_id=None,
        member_id=0,
        created_at=utcnow(),
        updated_at=utcnow(),
    )


@pytest.fixture
async def nav_cache():
    invalidate_macro_cache()
    yield NavigationMacroCache(ttl_seconds=3600)


@pytest.mark.asyncio
async def test_navigation_macro_cache_loads_from_db(_real_db, nav_cache):
    async with session_scope() as session:
        session.add(_make_nav_macro("显示主界面", "/chat", "已回到主界面"))
        session.add(_make_nav_macro("show main window", "/chat", "Returned to main"))

    info = await nav_cache.get("显示主界面")
    assert info is not None
    assert info.route == "/chat"
    assert info.feedback == "已回到主界面"

    info_en = await nav_cache.get("show main window")
    assert info_en is not None
    assert info_en.route == "/chat"


@pytest.mark.asyncio
async def test_navigation_macro_cache_ignores_non_navigation_macros(_real_db, nav_cache):
    async with session_scope() as session:
        session.add(_make_nav_macro("打开微信", "/wechat", ""))
        # Non-active macro should not be returned.
        inactive = _make_nav_macro("隐藏", "__HIDE__", "")
        inactive.is_active = False
        session.add(inactive)

    info = await nav_cache.get("打开微信")
    assert info is not None
    assert info.route == "/wechat"

    assert await nav_cache.get("隐藏") is None


@pytest.mark.asyncio
async def test_command_router_resolves_navigation_macro(_real_db, nav_cache):
    async with session_scope() as session:
        session.add(_make_nav_macro("显示主窗口", "/chat", "已回到主界面"))

    router = CommandRouter(nav_macro_cache=nav_cache)
    decision = await router.resolve("显示主窗口", thread_id="t1", project_id=0, source="voice")

    assert decision.status == "routed"
    assert decision.target_type == "macro"
    assert decision.target.get("type") == "macro"
    assert isinstance(decision.target.get("id"), int)
    assert decision.params.get("route") == "/chat"
    assert decision.params.get("feedback") == "已回到主界面"
    assert decision.confidence == 1.0


@pytest.mark.asyncio
async def test_command_router_navigation_macro_miss_falls_through(_real_db, nav_cache):
    async with session_scope() as session:
        session.add(_make_nav_macro("显示主界面", "/chat", ""))

    router = CommandRouter(nav_macro_cache=nav_cache)
    decision = await router.resolve("不存在的命令", thread_id="t1", project_id=0, source="voice")

    assert decision.target_type != "macro"
