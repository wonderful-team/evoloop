"""Cancellation-safe AsyncSession：aborted request 不再把连接滞留在池外。

背景（2026-09-19 复现定位）：全仓有十余处 ``async with session_factory() as session``
裸形态（codebase 检索/索引、project sync 等）。``AsyncSession.__aexit__`` 的
``await self.close()`` 不设防：取消恰好落在该 await（uvicorn/anyio 双重 cancel、
``asyncio.timeout`` 逃逸场景），close 被跳过 → 连接滞留在池外等 GC
（即 20 路并发 abort 后 "task FINISHED 但连接未还" 的灰色状态；watchdog/
GC 兜底回收但伴随 "non-checked-in connection" 告警）。

``get_db``/``session_scope`` 已有 ``_shielded_session_close``，但只保护显式
经它的路径。本类在 session 层统一免疫：所有使用形态（裸 ``async with`` 亦
包括）close 时对取消设防，取消语义不变（CancelledError 照常向外传播），
inner close 后台跑完、fairy 必回池。
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession


class LeakGuardAsyncSession(AsyncSession):
    """close() 经 shield 执行：调用方被取消不阻断连接归还。"""

    async def close(self) -> None:
        await asyncio.shield(AsyncSession.close(self))
