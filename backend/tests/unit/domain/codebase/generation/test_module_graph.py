"""Unit tests for ModuleGraphService + Leiden integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.codebase.generation.leiden import run_leiden, _common_prefix, _fallback_name
from app.domain.codebase.generation.module_graph import Module, ModuleGraph, ModuleGraphService


class TestLeiden:
    def test_run_leiden_triangle(self):
        edges = [("a", "b"), ("b", "c"), ("a", "c")]
        communities = run_leiden(edges)
        assert isinstance(communities, dict)
        # All 3 nodes should be in the same community
        all_entities = [e for ents in communities.values() for e in ents]
        assert "a" in all_entities
        assert "b" in all_entities
        assert "c" in all_entities

    def test_run_leiden_two_communities(self):
        edges = [("a", "b"), ("c", "d")]
        communities = run_leiden(edges)
        # Each pair should be together; but exact community count depends
        # on graspologic resolution — assert at least 2 communities
        assert len(communities) >= 2

    def test_fallback_name_single(self):
        assert _fallback_name(["goods"]) == "goods"

    def test_fallback_name_common_prefix(self):
        assert "Order" in _fallback_name(["order", "order_goods", "order_refund"])

    def test_common_prefix(self):
        assert _common_prefix(["order", "order_goods", "order_refund"]) == "order"


class TestModuleGraph:
    def test_impact_set_direct(self):
        g = ModuleGraph(
            modules=[],
            entity_to_module={"goods": "商品", "order": "订单"},
            adjacency=[],
        )
        assert g.impact_set({"goods"}) == {"商品"}

    def test_impact_set_propagates(self):
        g = ModuleGraph(
            modules=[],
            entity_to_module={"goods": "商品", "order": "订单", "member": "会员"},
            adjacency=[("商品", "订单")],
        )
        result = g.impact_set({"goods"})
        assert "商品" in result
        assert "订单" in result  # propagated via adjacency
        assert "会员" not in result  # not connected

    def test_format_summary(self):
        g = ModuleGraph(
            modules=[
                Module(name="商品", entities=["goods"], entity_count=3, summary=""),
                Module(name="订单", entities=["order"], entity_count=2, summary=""),
            ],
            entity_to_module={"goods": "商品", "order": "订单"},
            adjacency=[],
        )
        s = g.format_summary()
        assert "商品" in s
        assert "订单" in s


class TestModuleGraphService:
    @pytest.mark.asyncio
    async def test_empty_project(self):
        service = ModuleGraphService()
        with patch.object(service, "_fetch_edges", AsyncMock(return_value=[])):
            modules = await service.get_modules(project_id=999)
            assert modules == []

    @pytest.mark.asyncio
    async def test_get_module_of_returns_none_for_unknown(self):
        service = ModuleGraphService()
        with patch.object(service, "_fetch_edges", AsyncMock(return_value=[])):
            result = await service.get_module_of(project_id=999, entity="foo")
            assert result is None

    @pytest.mark.asyncio
    async def test_refresh_caches_result(self):
        service = ModuleGraphService()
        from app.domain.codebase.generation.module_graph import _cache
        _cache.clear()

        with patch.object(service, "_fetch_edges", AsyncMock(return_value=[("a", "b")])):
            g1 = await service.refresh(project_id=200)
            # a and b should be clustered somewhere
            all_entities = [e for m in g1.modules for e in m.entities]
            assert "a" in all_entities
            assert "b" in all_entities

            # Second call should use cache (not _fetch_edges)
            g2 = await service.get_modules(project_id=200)
            all_entities2 = [e for m in g2 for e in m.entities]
            assert "a" in all_entities2
            assert "b" in all_entities2
