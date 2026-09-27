"""页面预选契约（capability-packages-refactor.md §9.5 + G4）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.core.context.schemas import ContextMetadata
from app.core.engine.preselection import resolve_preselection


class TestResolvePreselection:
    """预选解析（v3）：域→包目录走 DB，页面预挂 = route_patterns 匹配。"""

    def _pkgs(self):
        orders = MagicMock()
        orders.name = "mall-orders"
        orders.capability = {
            "domain": "mall_ops",
            "route_patterns": ["order", "shipping"],
        }
        products = MagicMock()
        products.name = "mall-products"
        products.capability = {"domain": "mall_ops", "route_patterns": ["goods"]}
        return [orders, products]

    async def test_route_pattern_match(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
            AsyncMock(return_value=self._pkgs()),
        )
        out = await resolve_preselection("mall_ops", {"route": "order/management"})
        assert out == ["mall-orders"]

    async def test_no_route_match_empty(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
            AsyncMock(return_value=self._pkgs()),
        )
        assert await resolve_preselection("mall_ops", {"route": "zzz/x"}) == []
        assert await resolve_preselection("mall_ops", {"route": ""}) == []

    async def test_no_domain_empty(self, monkeypatch) -> None:
        assert await resolve_preselection(None, {"route": "order/x"}) == []

    async def test_empty_domain_no_packages(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
            AsyncMock(return_value=[]),
        )
        assert await resolve_preselection("other_domain", {"route": "order/x"}) == []


class TestSurfaceMerge:
    """预选 ∪ 加载合成 + G4 confirm_tools 排除。"""

    def _ctx(self, loaded=(), preselected=()):
        ctx = MagicMock()
        ctx.metadata = ContextMetadata(
            loaded_packages=list(loaded), preselected_packages=list(preselected)
        )
        return ctx

    async def test_preselected_excludes_confirm_tools(self, monkeypatch) -> None:
        from app.core.tools.manager import tool_manager

        monkeypatch.setattr(
            "app.core.context.ContextManager.current",
            staticmethod(lambda: self._ctx(preselected=["mall-refunds"])),
        )

        async def fake_cap(_name, _wd=None):
            return {
                "tools": [
                    {
                        "mcp_server": "capability-matrix",
                        "include": ["query_refund", "refund_transfer"],
                    }
                ],
                "confirm_tools": ["refund_transfer"],
            }

        monkeypatch.setattr(
            "app.core.learning.skills.discovery.skill_discovery.get_capability",
            fake_cap,
        )
        surface = await tool_manager._resolve_package_surface()
        exact, full, excluded = surface
        assert exact["capability_matrix"] == {"query_refund"}
        assert excluded["capability_matrix"] == {"refund_transfer"}

    async def test_loaded_package_releases_confirm_tools(self, monkeypatch) -> None:
        from app.core.tools.manager import tool_manager

        monkeypatch.setattr(
            "app.core.context.ContextManager.current",
            staticmethod(
                lambda: self._ctx(loaded=["mall-refunds"], preselected=["mall-refunds"])
            ),
        )

        async def fake_cap(_name, _wd=None):
            return {
                "tools": [
                    {
                        "mcp_server": "capability-matrix",
                        "include": ["query_refund", "refund_transfer"],
                    }
                ],
                "confirm_tools": ["refund_transfer"],
            }

        monkeypatch.setattr(
            "app.core.learning.skills.discovery.skill_discovery.get_capability",
            fake_cap,
        )
        surface = await tool_manager._resolve_package_surface()
        exact, _, excluded = surface
        assert exact["capability_matrix"] == {"query_refund", "refund_transfer"}
        assert excluded == {}

    async def test_merge_dedupes_loaded_vs_preselected(self, monkeypatch) -> None:
        from app.core.tools.manager import tool_manager

        monkeypatch.setattr(
            "app.core.context.ContextManager.current",
            staticmethod(
                lambda: self._ctx(loaded=["mall-orders"], preselected=["mall-orders"])
            ),
        )

        async def fake_cap(_name, _wd=None):
            return {"tools": [{"mcp_server": "s1", "include": ["t1"]}]}

        monkeypatch.setattr(
            "app.core.learning.skills.discovery.skill_discovery.get_capability",
            fake_cap,
        )
        surface = await tool_manager._resolve_package_surface()
        exact, _, excluded = surface
        assert exact == {"s1": {"t1"}}
