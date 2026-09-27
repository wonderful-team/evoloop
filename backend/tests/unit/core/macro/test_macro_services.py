"""Unit tests for the macro service layer added during refactoring.

Covers: create_for_skill (G6 pairing), list_routable_macros (G2 directory
service), and extract_navigation_url (G9 navigation URL extraction).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.learning.macro.runner import extract_navigation_url
from app.core.learning.macro.service import MacroService


def _macro(id_, name, macro_script, trigger_patterns=None, project_id=None, namespace="preset", created_at=None):
    m = SimpleNamespace(
        id=id_,
        name=name,
        macro_script=macro_script,
        trigger_patterns=trigger_patterns or [],
        project_id=project_id,
        namespace=namespace,
        created_at=created_at,
        macro_id=id_,
        description="",
        feedback="",
    )
    return m


class TestListRoutableMacros:
    @pytest.mark.asyncio
    async def test_orders_preset_first_newest_first(self, monkeypatch):
        now = pytest.importorskip("datetime").datetime(2024, 1, 1)
        m_old = _macro(1, "m1", "x", namespace="project", created_at=now)
        m_preset = _macro(2, "m2", "x", namespace="preset", created_at=now)
        m_new = _macro(3, "m3", "x", namespace="project", created_at=now.replace(day=2))

        async def fake_list_macros(**kwargs):
            assert kwargs.get("status") == "verified"
            assert kwargs.get("is_active") is True
            return [m_new, m_old, m_preset]

        monkeypatch.setattr(
            "app.core.learning.macro.lifecycle.list_macros", fake_list_macros
        )
        result = await MacroService.list_routable_macros()
        assert [m.id for m in result] == [2, 3, 1]  # preset, then newest

    @pytest.mark.asyncio
    async def test_filters_namespace(self, monkeypatch):
        async def fake_list_macros(**kwargs):
            assert kwargs.get("namespace") == "preset"
            return []

        monkeypatch.setattr(
            "app.core.learning.macro.lifecycle.list_macros", fake_list_macros
        )
        await MacroService.list_routable_macros(namespace="preset")


class TestCreateForSkill:
    @pytest.mark.asyncio
    async def test_links_skill_macro_id(self, monkeypatch):
        created_macro = _macro(99, "paired", "script")

        async def fake_create_from_synthesis(db, **kwargs):
            assert kwargs.get("fallback_skill_id") == 7
            assert kwargs.get("name") == "my-skill"
            return created_macro

        monkeypatch.setattr(
            "app.core.learning.macro.lifecycle.create_macro_from_synthesis",
            fake_create_from_synthesis,
        )
        skill = SimpleNamespace(
            id=7,
            name="my-skill",
            description="desc",
            trigger_patterns=["t"],
            parameters=[{"name": "p", "type": "string"}],
            macro_id=None,
        )
        macro = await MacroService.create_for_skill(
            db=None, skill=skill, macro_script="script", project_id=1, member_id=2
        )
        assert macro.id == 99
        assert skill.macro_id == 99


class TestExtractNavigationUrl:
    def test_navigate_url(self):
        m = _macro(1, "m", """steps:
- type: action
  event_type: navigate
  payload:
    url: "{{base_url}}/shop.html"
""")
        assert extract_navigation_url(m) == "{{base_url}}/shop.html"

    def test_goto_url(self):
        m = _macro(2, "m", """steps:
- type: action
  event_type: goto
  payload:
    url: "/admin/orders"
""")
        assert extract_navigation_url(m) == "/admin/orders"

    def test_frontend_navigate_route(self):
        m = _macro(3, "m", """steps:
- event_type: frontend_navigate
  payload:
    route: /orders
""")
        assert extract_navigation_url(m) == "/orders"

    def test_bad_script_returns_none(self):
        m = _macro(4, "m", "bad: [")
        assert extract_navigation_url(m) is None

    def test_no_navigate_returns_none(self):
        m = _macro(5, "m", """steps:
- type: action
  event_type: wait
  payload:
    seconds: 1
""")
        assert extract_navigation_url(m) is None

class TestResolveNavigationMacro:
    @pytest.mark.asyncio
    async def test_exact_phrase_match(self, monkeypatch):
        nav = _macro(
            1,
            "导航到订单",
            """steps:
- event_type: frontend_navigate
  payload:
    route: /orders
""",
            trigger_patterns=["查看订单", "订单"],
        )
        nav.feedback = "跳转订单页"

        async def fake_list(project_id=None, namespace=None):
            return [nav]

        monkeypatch.setattr(
            "app.core.learning.macro.service.MacroService.list_routable_macros",
            fake_list,
        )
        result = await MacroService.resolve_navigation_macro("订单")
        assert result == (1, "/orders", "跳转订单页")

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self, monkeypatch):
        nav = _macro(
            1,
            "m",
            """steps:
- event_type: frontend_navigate
  payload:
    route: /orders
""",
            trigger_patterns=["查看订单"],
        )

        async def fake_list(project_id=None, namespace=None):
            return [nav]

        monkeypatch.setattr(
            "app.core.learning.macro.service.MacroService.list_routable_macros",
            fake_list,
        )
        assert await MacroService.resolve_navigation_macro("退款") is None

    @pytest.mark.asyncio
    async def test_non_navigation_macro_skipped(self, monkeypatch):
        m = _macro(2, "m", "steps:\n- type: action\n  event_type: wait", trigger_patterns=["x"])

        async def fake_list(project_id=None, namespace=None):
            return [m]

        monkeypatch.setattr(
            "app.core.learning.macro.service.MacroService.list_routable_macros",
            fake_list,
        )
        assert await MacroService.resolve_navigation_macro("x") is None


class TestReconcileForSkill:
    @pytest.mark.asyncio
    async def test_uses_existing_macro_id(self, monkeypatch):
        skill = SimpleNamespace(id=1, macro_id=10, name="s", description="d",
                                trigger_patterns=["t"], parameters=[], project_id=None, member_id=0)

        async def fake_update(mid, fields, db=None):
            return True

        monkeypatch.setattr(
            "app.core.learning.macro.lifecycle.update_macro", fake_update
        )
        result = await MacroService.reconcile_for_skill(
            db=None, skill=skill, macro_script="script"
        )
        assert result == 10
        assert skill.macro_id == 10

    @pytest.mark.asyncio
    async def test_reuses_by_fallback_skill_id(self, monkeypatch):
        skill = SimpleNamespace(id=1, macro_id=None, name="s", description="d",
                                trigger_patterns=["t"], parameters=[], project_id=None, member_id=0)
        existing = _macro(7, "s", "x")

        async def fake_list_macros(fallback_skill_id=None, db=None):
            return [existing]

        async def fake_update(mid, fields, db=None):
            return True

        monkeypatch.setattr(
            "app.core.learning.macro.lifecycle.list_macros", fake_list_macros
        )
        monkeypatch.setattr(
            "app.core.learning.macro.lifecycle.update_macro", fake_update
        )
        result = await MacroService.reconcile_for_skill(
            db=None, skill=skill, macro_script="script"
        )
        assert result == 7
        assert skill.macro_id == 7

    @pytest.mark.asyncio
    async def test_creates_when_no_existing(self, monkeypatch):
        skill = SimpleNamespace(id=1, macro_id=None, name="s", description="d",
                                trigger_patterns=["t"], parameters=[], project_id=None, member_id=0)
        created = _macro(99, "s", "x")

        async def fake_list_macros(fallback_skill_id=None, db=None):
            return []

        async def fake_create(db, **kwargs):
            assert kwargs.get("fallback_skill_id") == 1
            return created

        monkeypatch.setattr(
            "app.core.learning.macro.lifecycle.list_macros", fake_list_macros
        )
        monkeypatch.setattr(
            "app.core.learning.macro.lifecycle.create_macro_from_synthesis", fake_create
        )
        result = await MacroService.reconcile_for_skill(
            db=None, skill=skill, macro_script="script"
        )
        assert result == 99
        assert skill.macro_id == 99


