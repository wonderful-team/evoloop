"""DatabaseCallbackHandler skip_persistence tests.

覆盖 skip_message_persistence 修复：run 级 skip 标志应让 tool 消息（RUNNING +
COMPLETED/FAILED）不落库，修复此前 tool 消息绕过 skip、产生孤儿记录的断裂。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.core.engine.callbacks.database_logger import DatabaseCallbackHandler


@pytest.fixture(autouse=True)
async def _real_db(tmp_path, monkeypatch):
    """自备真实文件 DB（此前搭便车于其他测试的初始化，验收层加入后被清掉）。"""
    monkeypatch.setattr(settings, "SQLITE_PATH", str(tmp_path / "backend.db"))
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=True)
    yield
    # 只拆本 loop 的资源：shutdown() 是全局 teardown，会 dispose 其它
    # fixture 注册的引擎并清空 manager 状态（2026-09-19 组合漂移根因之一）。
    loop = db_resource_manager._current_loop()
    eng = db_resource_manager._engines.pop(loop, None)
    db_resource_manager._session_factories.pop(loop, None)
    vs = db_resource_manager._vector_stores.pop(loop, None)
    if vs is not None and hasattr(vs, "close"):
        vs.close()
    if eng is not None:
        await eng.dispose()
    # 与旧全局 shutdown 语义对齐：本 fixture initialize 出来的 sync engine
    # 必须一并摘除，否则残留的 _sync_engine 指向本测试 tmp 文件库，
    # 后续测试的同步路径会读到"有表无数据"的幽灵库。
    if db_resource_manager._sync_engine is not None:
        db_resource_manager._sync_engine.dispose()
        db_resource_manager._sync_engine = None



def _make_handler(skip_persistence: bool = False):
    h = DatabaseCallbackHandler(
        thread_id="t-1", project_id=1, run_id="r-1", skip_persistence=skip_persistence
    )
    h._handler.handle_tool_start = AsyncMock(
        return_value=SimpleNamespace(sequence_number=5)
    )
    h._handler.handle_tool_output = AsyncMock(
        return_value={"category": "tool_output", "persisted": True}
    )
    h._handler.handle_tool_error = AsyncMock()
    return h


def _ctx():
    return SimpleNamespace(
        current_tool_call_id=None,
        injected_secrets=[],
        thread_id="t-1",
        member_id=1,
        project_id=1,
    )


@pytest.mark.asyncio
async def test_skip_tool_start_does_not_persist():
    h = _make_handler(skip_persistence=True)
    from uuid import uuid4

    rid = uuid4()
    with patch(
        "app.core.context.manager.ContextManager.current", return_value=_ctx()
    ):
        await h.on_tool_start({"name": "read"}, '{"path":"/tmp/x"}', run_id=rid)
    assert h._handler.handle_tool_start.await_count == 0


@pytest.mark.asyncio
async def test_skip_tool_end_does_not_persist():
    h = _make_handler(skip_persistence=True)
    from uuid import uuid4

    rid = uuid4()
    with patch(
        "app.core.context.manager.ContextManager.current", return_value=_ctx()
    ):
        await h.on_tool_start({"name": "read"}, '{"path":"/tmp/x"}', run_id=rid)
        await h.on_tool_end("output", run_id=rid)
    assert h._handler.handle_tool_output.await_count == 0


@pytest.mark.asyncio
async def test_skip_tool_error_does_not_persist():
    h = _make_handler(skip_persistence=True)
    from uuid import uuid4

    rid = uuid4()
    with patch(
        "app.core.context.manager.ContextManager.current", return_value=_ctx()
    ):
        await h.on_tool_start({"name": "read"}, '{"path":"/tmp/x"}', run_id=rid)
        await h.on_tool_error(Exception("boom"), run_id=rid)
    assert h._handler.handle_tool_error.await_count == 0


@pytest.mark.asyncio
async def test_non_skip_still_persists():
    h = _make_handler(skip_persistence=False)
    from uuid import uuid4

    rid = uuid4()
    with patch(
        "app.core.context.manager.ContextManager.current", return_value=_ctx()
    ):
        await h.on_tool_start({"name": "read"}, '{"path":"/tmp/x"}', run_id=rid)
        await h.on_tool_end("output", run_id=rid)
    assert h._handler.handle_tool_start.await_count == 1
    assert h._handler.handle_tool_output.await_count == 1
