"""搜索工具并发逻辑的单元测试（stub 引擎，无真实网络）。

覆盖 search_web 的三引擎并发先到先得 + 8s 硬上限。
"""

from __future__ import annotations

import asyncio

import pytest

from app.domain.tools import research

pytestmark = pytest.mark.unit


class _EngineStub:
    """可编程的搜索 stub：delay 后返回给定结果。"""

    def __init__(self, delay: float, results: list[str] | None) -> None:
        self.delay = delay
        self.results = results
        self.cancelled = False

    async def __call__(self, query: str) -> list[str] | None:
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.results


class TestSearchParallel:
    def _patch_engines(self, monkeypatch, stubs: dict[str, _EngineStub]) -> None:
        monkeypatch.setattr(research, "_search_duckduckgo", stubs["ddg"])
        monkeypatch.setattr(research, "_search_baidu", stubs["baidu"])
        monkeypatch.setattr(research, "_search_wikipedia", stubs["wiki"])

    async def test_fast_wins_does_not_wait_for_slow(self, monkeypatch) -> None:
        """快者有结果 → 立即返回，慢者被取消。"""
        fast = _EngineStub(0.05, ["fast result"])
        slow = _EngineStub(5.0, ["slow result"])
        self._patch_engines(monkeypatch, {"ddg": slow, "baidu": fast, "wiki": slow})
        t0 = asyncio.get_event_loop().time()
        result = await research._search_parallel("q")
        elapsed = asyncio.get_event_loop().time() - t0
        assert result == ["fast result"]
        assert elapsed < 1.0, f"不应等待慢引擎，实际 {elapsed:.2f}s"
        assert slow.cancelled, "慢引擎任务应被取消"

    async def test_slow_is_only_provider(self, monkeypatch) -> None:
        """只有慢者有结果 → 等待它返回。"""
        slow = _EngineStub(0.2, ["slow result"])
        self._patch_engines(
            monkeypatch,
            {"ddg": _EngineStub(0.05, None), "baidu": _EngineStub(0.05, None), "wiki": slow},
        )
        assert await research._search_parallel("q") == ["slow result"]

    async def test_all_empty_returns_none(self, monkeypatch) -> None:
        """全部引擎返回空 → None。"""
        self._patch_engines(
            monkeypatch,
            {"ddg": _EngineStub(0.02, None), "baidu": _EngineStub(0.02, None), "wiki": _EngineStub(0.02, None)},
        )
        assert await research._search_parallel("q") is None

    async def test_overall_timeout_caps_worst_case(self, monkeypatch) -> None:
        """全部慢 → 受 _SEARCH_PARALLEL_TIMEOUT 硬上限约束返回 None。"""
        monkeypatch.setattr(research, "_SEARCH_PARALLEL_TIMEOUT", 0.3)
        slow = _EngineStub(2.0, ["too late"])
        self._patch_engines(monkeypatch, {"ddg": slow, "baidu": slow, "wiki": slow})
        t0 = asyncio.get_event_loop().time()
        result = await research._search_parallel("q")
        elapsed = asyncio.get_event_loop().time() - t0
        assert result is None
        assert elapsed < 1.0, f"硬上限应生效，实际 {elapsed:.2f}s"
