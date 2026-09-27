"""Per-test DB stub（unit 共享）。

``db_resource_manager`` 改为 loop 对象弱键后（2026-09-19 id-reuse 修复），
``initialize()`` 的短路条件是 ``loop in self._engines``。只 patch
``_session_factories`` 的 fixture 不再安全：测试 loop 内任何路由/依赖触发
``initialize()`` 都会把 patch 字典覆写回真实 factory（其引擎随 loop 关闭而
GC，表现为后续查询 "Cannot operate on a closed database"）。

本 helper 同时登记 ``_engines[loop]``，让 initialize() 短路，并统一使用
LeakGuardAsyncSession 与显式 dispose。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def stub_db_for_loop(monkeypatch: Any, engine: AsyncEngine):
    """把 engine/factory 登记为当前 loop 的 DB 资源，返回 session factory。"""
    from app.infrastructure.database import resource_manager
    from app.infrastructure.database.guarded_session import LeakGuardAsyncSession

    mgr = resource_manager.db_resource_manager
    loop = mgr._current_loop()
    factory = async_sessionmaker(
        engine, class_=LeakGuardAsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(mgr, "_session_factories", {loop: factory})
    monkeypatch.setattr(mgr, "_engines", {loop: engine})
    return factory
