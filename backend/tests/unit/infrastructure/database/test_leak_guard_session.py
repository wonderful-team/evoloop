"""LeakGuardAsyncSession 契约（2026-09-19 并发 abort 灰色状态归零）。

形状：任务持有已 checkout 的连接（``async with factory()`` 裸形态，codebase
检索/索引等十余处同款），双次 cancel 令第二次恰好落在 ``__aexit__`` 的
close await 上：

- 裸 ``AsyncSession``：close 被取消吞掉 → 连接滞留池外（复现灰色状态）；
- ``LeakGuardAsyncSession``：shield 内层后台跑完 → fairy 必回池，
  且取消语义不变（任务仍 CANCELLED）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.infrastructure.database.guarded_session import LeakGuardAsyncSession


def _engine(tmp_path: Path):
    return create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/t.db",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=5,
        max_overflow=25,
    )


async def _aborted_body(factory):
    async with factory() as session:
        await session.execute(text("SELECT 1"))
        await asyncio.sleep(5)  # 持有连接时被 abort


async def _double_cancel_drain(engine, factory):
    task = asyncio.create_task(_aborted_body(factory))
    await asyncio.sleep(0.15)
    task.cancel()
    task.cancel()  # 第二次：落在 __aexit__ 的 close await 上
    with pytest.raises(asyncio.CancelledError):
        await task
    for _ in range(20):
        await asyncio.sleep(0.05)
    return engine.pool.checkedout()


@pytest.mark.asyncio
async def test_leak_guard_survives_double_cancel(tmp_path):
    engine = _engine(tmp_path)
    factory = async_sessionmaker(engine, class_=LeakGuardAsyncSession, expire_on_commit=False)
    try:
        assert await _double_cancel_drain(engine, factory) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_normal_close_semantics_unchanged(tmp_path):
    engine = _engine(tmp_path)
    factory = async_sessionmaker(engine, class_=LeakGuardAsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        assert engine.pool.checkedout() == 0
        async with factory() as session:
            await session.execute(text("SELECT 1"))
            await session.close()
        assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose()
