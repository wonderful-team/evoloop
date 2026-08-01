"""Sanity checks for navigation macros resolved via the DB macro system."""

import pytest

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
async def zh_nav_router(_real_db):
    cache = NavigationMacroCache(ttl_seconds=3600)
    async with session_scope() as session:
        session.add(_make_nav_macro("显示主窗口", "/chat", "已回到主界面"))

    yield CommandRouter(nav_macro_cache=cache)


@pytest.mark.asyncio
async def test_zh_show_main_window_is_navigation_macro(zh_nav_router):
    decision = await zh_nav_router.resolve(
        "显示主窗口", thread_id="t1", project_id=0, source="voice"
    )
    assert decision.status == "routed"
    assert decision.target_type == "macro"
    assert decision.params.get("route") == "/chat"
    assert decision.params.get("feedback") == "已回到主界面"
