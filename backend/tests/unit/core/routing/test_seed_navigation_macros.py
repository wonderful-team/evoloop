"""Verify the navigation macro seed script populates the DB correctly."""

import pytest

from scripts.seed_navigation_macros import (
    _load_nav_routes,
    _navigation_macro_script,
)


@pytest.fixture
def temp_nav_routes(tmp_path, monkeypatch):
    """Create a temporary nav_routes.yaml and point the seed script at it."""
    routes_path = tmp_path / "nav_routes.yaml"
    routes_path.write_text(
        "nav_routes:\n"
        "- phrase: 显示主界面\n"
        "  route: /chat\n"
        "  feedback: 已回到主界面\n"
        "- phrase: 打开聊天\n"
        "  route: /chat\n"
        "  feedback: 已回到主界面\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("scripts.seed_navigation_macros.NAV_ROUTES_PATH", routes_path)
    return routes_path


@pytest.mark.asyncio
async def test_seed_navigation_macros_creates_records(_real_db, temp_nav_routes):  # noqa: ARG001
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.macro import Macro
    from scripts import seed_navigation_macros

    await seed_navigation_macros.main()

    async with session_scope() as session:
        nav_macros = (await session.execute(
            select(Macro).where(Macro.namespace == "preset")
        )).scalars().all()

    phrases = {m.name for m in nav_macros}
    assert "显示主界面" in phrases
    assert "打开聊天" in phrases

    for macro in nav_macros:
        assert "frontend_navigate" in macro.macro_script
        assert macro.is_active is True
        assert macro.status == "verified"


def test_load_nav_routes_reads_yaml(temp_nav_routes):  # noqa: ARG001
    entries = _load_nav_routes()
    phrases = {e["phrase"] for e in entries}
    assert "显示主界面" in phrases
    assert "打开聊天" in phrases
    assert entries[0]["route"]
    assert entries[0]["feedback"]


def test_navigation_macro_script_contains_route():
    script = _navigation_macro_script("/chat")
    assert "frontend_navigate" in script
    assert "route: /chat" in script
