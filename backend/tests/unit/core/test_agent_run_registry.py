"""Tests for AgentRunRegistry cascade cancel (docs/worker-delegation-design.md Phase A).

A Worker split spawns subagents whose run parent is ``<tid>-split-*``. Cancelling
the parent Worker must cascade-cancel those split subagents.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.engine.agent_run_registry import agent_run_registry


@pytest.mark.asyncio
class TestAgentRunRegistryCascadeCancel:
    @pytest.fixture(autouse=True)
    def _clean(self):
        agent_run_registry._records.clear()
        yield
        agent_run_registry._records.clear()

    async def _running_task(self):
        async def body():
            await asyncio.sleep(10)

        return asyncio.create_task(body())

    async def test_cancel_run_cascades_split_subagents(self):
        parent = await self._running_task()
        child1 = await self._running_task()
        child2 = await self._running_task()
        unrelated = await self._running_task()

        await agent_run_registry.register_run("t1", parent, "parent worker")
        await agent_run_registry.register_run("t1-split-sub-0", child1, "split 1")
        await agent_run_registry.register_run("t1-split-sub-1", child2, "split 2")
        await agent_run_registry.register_run("t2", unrelated, "other thread")

        assert await agent_run_registry.cancel_run("t1") is True
        await asyncio.sleep(0.01)

        # 父 + split 子任务全部取消；无关线程不受影响
        assert parent.cancelled()
        assert child1.cancelled()
        assert child2.cancelled()
        assert not unrelated.cancelled()
        # split 子任务从注册表移除
        assert await agent_run_registry.get_run("t1-split-sub-0") is None

    async def test_cancel_unknown_thread_returns_false(self):
        assert await agent_run_registry.cancel_run("nonexistent") is False

    async def test_cancel_split_only_when_parent_missing(self):
        """父 Worker 已不在注册表（如已完成），但 split 子任务仍级联取消。"""
        child = await self._running_task()
        await agent_run_registry.register_run("t9-split-sub-0", child, "split")
        assert await agent_run_registry.cancel_run("t9") is True
        await asyncio.sleep(0.01)
        assert child.cancelled()
