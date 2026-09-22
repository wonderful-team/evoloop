"""HITL 授权台账（终态 v2）真实 DB 行为测试。

覆盖四条终态语义的落地实现（区别于 mock 层契约测试）：
1. create_request 的结构化资源锚点（resource_path/resource_action 落库）；
2. mark_thread_resource_rejected 拒绝台账：插入/续期/关闭 pending；
3. has_thread_resource_rejection 列精确匹配（/Users/foo 不得误杀 /Users/foo2）
   + TTL 过期自动解封 + 线程隔离；
4. was_call_recently_approved 跨进程认领窗口（双轨 COMPLETED+APPROVED）。

数据源契约：路径判断只查 human_requests.resource_path 列（归一化绝对路径），
禁止 description 文本子串匹配。
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.hitl.core import create_request, finalize_request
from tests.unit.db_stub import stub_db_for_loop

APPROVED = "APPROVED"
REJECTED = "REJECTED"


@pytest.fixture
async def _hitl_db(monkeypatch):
    """In-memory aiosqlite engine patched into db_resource_manager."""

    from app.models import Message
    from app.models.conversation import HumanRequest

    engine = create_async_engine("sqlite+aiosqlite://")
    factory = stub_db_for_loop(monkeypatch, engine)
    async with factory() as session:
        await session.run_sync(
            lambda sess: HumanRequest.__table__.create(
                sess.get_bind(), checkfirst=True
            )
        )
        await session.run_sync(
            lambda sess: Message.__table__.create(sess.get_bind(), checkfirst=True)
        )
    yield factory
    await engine.dispose()


async def _fetch_requests(factory, **filters):
    from sqlalchemy import select

    from app.models.conversation import HumanRequest

    async with factory() as session:
        res = await session.execute(
            select(HumanRequest).filter_by(**filters).order_by(HumanRequest.created_at)
        )
        return list(res.scalars().all())


async def _add_hitl_message(
    factory,
    thread_id: str,
    tool_call_id: str,
    request_id: str,
    status: str = "waiting_human",
    updated_at=None,
):
    """模拟引擎侧中断时落库的 hitl_request 消息（双轨的 messages 轨）。"""
    from app.models import Message
    from app.utils.id import gen_uuid

    async with factory() as session:
        session.add(
            Message(
                id=gen_uuid(),
                thread_id=thread_id,
                role="system",
                category="hitl_request",
                tool_call_id=tool_call_id,
                status=status,
                meta_data={"hitl_request_id": request_id},
                content='{"type": "approval"}',
                updated_at=updated_at,
            )
        )
        await session.commit()


# ============ create_request 结构化锚点 ============


@pytest.mark.asyncio
async def test_create_request_persists_resource_anchor(_hitl_db):
    """request_authorization 创建的审批行必须带 resource_path/resource_action
    （拒绝判死 / 近期放行查询的数据源）。"""
    req = await create_request(
        thread_id="t-1",
        request_type="approval",
        prompt="读取 /outside/a",
        context="ctx",
        default_value=REJECTED,
        resource_path="/outside/a",
        resource_action="read",
    )
    rows = await _fetch_requests_by_id(_hitl_db, req.id)
    assert len(rows) == 1
    assert rows[0].resource_path == "/outside/a"
    assert rows[0].resource_action == "read"
    assert rows[0].status == "pending"


async def _fetch_requests_by_id(factory, request_id):
    from sqlalchemy import select

    from app.models.conversation import HumanRequest

    async with factory() as session:
        res = await session.execute(select(HumanRequest).filter_by(id=request_id))
        return list(res.scalars().all())


# ============ 拒绝台账：插入 / 续期 / 关闭 pending ============


@pytest.mark.asyncio
async def test_mark_rejected_inserts_ledger_and_closes_pending(_hitl_db):
    from app.core.hitl.orchestrator import HITLOrchestrator

    req = await create_request(
        thread_id="t-1",
        request_type="approval",
        prompt="读取 /outside/a",
        resource_path="/outside/a",
        resource_action="read",
    )
    await HITLOrchestrator.mark_thread_resource_rejected("t-1", "/outside/a")

    # pending 行被关闭并补 expires_at
    rows = await _fetch_requests_by_id(_hitl_db, req.id)
    assert rows[0].status == "completed"
    assert rows[0].result == REJECTED
    assert rows[0].expires_at is not None

    # 台账行存在且带 TTL
    ledgers = await _fetch_requests(_hitl_db, thread_id="t-1", result=REJECTED)
    assert any(
        r.resource_path == "/outside/a" and r.expires_at is not None for r in ledgers
    )


@pytest.mark.asyncio
async def test_mark_rejected_renews_existing_ledger(_hitl_db):
    """同 key 重复拒绝 → 续期既有台账（不无限累积重复行）。"""
    from app.core.hitl.orchestrator import HITLOrchestrator

    await HITLOrchestrator.mark_thread_resource_rejected("t-1", "/outside/a")
    first = await _fetch_requests(_hitl_db, thread_id="t-1", result=REJECTED)
    assert len(first) == 1

    await HITLOrchestrator.mark_thread_resource_rejected("t-1", "/outside/a")
    second = await _fetch_requests(_hitl_db, thread_id="t-1", result=REJECTED)
    # 续期路径不得累积重复台账行
    assert len(second) == 1
    assert second[0].expires_at >= first[0].expires_at


# ============ 判死查询：精确匹配 / TTL / 线程域 ============


@pytest.mark.asyncio
async def test_has_rejection_no_prefix_false_positive(_hitl_db):
    """P1-4 回归：/Users/foo 的拒绝不得命中 /Users/foo2（子串误杀）。"""
    from app.core.hitl.orchestrator import HITLOrchestrator

    await HITLOrchestrator.mark_thread_resource_rejected("t-1", "/Users/foo")
    assert await HITLOrchestrator.has_thread_resource_rejection("t-1", "/Users/foo")
    assert not await HITLOrchestrator.has_thread_resource_rejection("t-1", "/Users/foo2")
    assert not await HITLOrchestrator.has_thread_resource_rejection(
        "t-1", "/Users/foo/sub"
    )


@pytest.mark.asyncio
async def test_has_rejection_expires_after_ttl(_hitl_db, monkeypatch):
    """拒绝 TTL 过期 → 判死失效（误拒自动解封出口）。"""
    from app.core.hitl import orchestrator as orch
    from app.core.hitl.orchestrator import HITLOrchestrator

    await HITLOrchestrator.mark_thread_resource_rejected("t-1", "/outside/a")
    assert await HITLOrchestrator.has_thread_resource_rejection("t-1", "/outside/a")

    real_utcnow = orch.utcnow
    monkeypatch.setattr(
        orch,
        "utcnow",
        lambda: real_utcnow() + timedelta(hours=25),
    )
    assert not await HITLOrchestrator.has_thread_resource_rejection("t-1", "/outside/a")


@pytest.mark.asyncio
async def test_has_rejection_thread_scoped(_hitl_db):
    """判死是线程级：其他线程不受影响（重新走 HITL）。"""
    from app.core.hitl.orchestrator import HITLOrchestrator

    await HITLOrchestrator.mark_thread_resource_rejected("t-1", "/outside/a")
    assert not await HITLOrchestrator.has_thread_resource_rejection("t-2", "/outside/a")


# ============ 近期放行认领（跨进程 DB 查询） ============


@pytest.mark.asyncio
async def test_was_call_recently_approved_full_chain(_hitl_db):
    """批准链路端到端：create → message(waiting_human) → finalize(APPROVED)
    → was_call_recently_approved True（双轨读到即为已批准）。"""
    from app.core.hitl.orchestrator import HITLOrchestrator

    req = await create_request(
        thread_id="t-1",
        request_type="approval",
        prompt="读取 /outside/a",
        resource_path="/outside/a",
        resource_action="read",
    )
    await _add_hitl_message(_hitl_db, "t-1", "call-1", req.id)
    claimed = await finalize_request(
        thread_id="t-1",
        request_id=req.id,
        tool_call_id="call-1",
        status="completed",
        response=APPROVED,
    )
    assert claimed is True
    assert await HITLOrchestrator.was_call_recently_approved("t-1", "call-1") is True


@pytest.mark.asyncio
async def test_was_call_recently_approved_false_on_rejected(_hitl_db):
    from app.core.hitl.orchestrator import HITLOrchestrator

    req = await create_request(
        thread_id="t-1",
        request_type="approval",
        prompt="读取 /outside/a",
        resource_path="/outside/a",
        resource_action="read",
    )
    await _add_hitl_message(_hitl_db, "t-1", "call-1", req.id)
    await finalize_request(
        thread_id="t-1",
        request_id=req.id,
        tool_call_id="call-1",
        status="completed",
        response=REJECTED,
    )
    # 拒绝不是放行：重执行不应被允许
    assert await HITLOrchestrator.was_call_recently_approved("t-1", "call-1") is False


@pytest.mark.asyncio
async def test_was_call_recently_approved_window_expiry(_hitl_db, monkeypatch):
    """认领窗口过期 → False（批准后长时间未重执行，后续新调用不再命中）。

    finalize 会把 messages.updated_at 刷新为批准时刻（onupdate），
    因此用冻结时钟前移窗口：批准发生在"11 分钟前" → 超出 600s 窗口。
    """
    from datetime import timedelta

    from app.core.hitl import orchestrator as orch
    from app.core.hitl.orchestrator import HITLOrchestrator

    req = await create_request(
        thread_id="t-1",
        request_type="approval",
        prompt="读取 /outside/a",
        resource_path="/outside/a",
        resource_action="read",
    )
    await _add_hitl_message(_hitl_db, "t-1", "call-1", req.id)
    await finalize_request(
        thread_id="t-1",
        request_id=req.id,
        tool_call_id="call-1",
        status="completed",
        response=APPROVED,
    )
    assert await HITLOrchestrator.was_call_recently_approved("t-1", "call-1") is True

    real_utcnow = orch.utcnow
    monkeypatch.setattr(
        orch,
        "utcnow",
        lambda: real_utcnow() + timedelta(seconds=601),
    )
    assert await HITLOrchestrator.was_call_recently_approved("t-1", "call-1") is False


@pytest.mark.asyncio
async def test_was_call_recently_approved_unknown_call(_hitl_db):
    from app.core.hitl.orchestrator import HITLOrchestrator

    assert await HITLOrchestrator.was_call_recently_approved("t-1", "call-none") is False
    assert await HITLOrchestrator.was_call_recently_approved("", "call-1") is False
    assert await HITLOrchestrator.was_call_recently_approved("t-1", "") is False


# ============ handle_resume：双轨定局 + 兄弟请求合并关闭（真实 DB） ============


async def _add_pending_hitl(
    factory,
    thread_id: str,
    tool_call_id: str,
    request_id: str,
    original_tool: dict,
):
    """一次 Agent 重试可能为同一工具+同参数产生多条 pending approval：
    每条 = 一行 human_requests(pending) + 一行 hitl_request 消息(waiting_human)。"""
    from app.models import Message
    from app.models.conversation import HumanRequest
    from app.utils.id import gen_uuid

    async with factory() as session:
        session.add(
            HumanRequest(
                id=request_id,
                thread_id=thread_id,
                type="approval",
                description=f"读取 {original_tool.get('args', {}).get('path', '')}",
                status="pending",
                resource_path=original_tool.get("args", {}).get("path"),
                resource_action="read",
            )
        )
        session.add(
            Message(
                id=gen_uuid(),
                thread_id=thread_id,
                role="system",
                category="hitl_request",
                tool_call_id=tool_call_id,
                tool_name=original_tool.get("name"),
                status="waiting_human",
                meta_data={
                    "hitl_request_id": request_id,
                    "original_tool": original_tool,
                },
                content='{"type": "approval"}',
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_handle_resume_finalizes_and_closes_sibling_requests(_hitl_db):
    """Agent 重试同一工具产生重复 pending：批准其中一条时，双轨原子关闭
    被批准请求，同工具+同参数的兄弟 pending 一并关闭（不留孤儿审批卡）。"""
    from unittest.mock import AsyncMock, patch

    from sqlalchemy import select

    from app.core.hitl.orchestrator import HITLOrchestrator
    from app.models import Message
    from app.models.conversation import HumanRequest

    tool = {"name": "bash", "args": {"command": "ls /outside"}}
    await _add_pending_hitl(_hitl_db, "t-1", "call-1", "req-1", original_tool=tool)
    await _add_pending_hitl(_hitl_db, "t-1", "call-2", "req-2", original_tool=tool)

    pending_tool = await HITLOrchestrator.get_pending_request("t-1", "m")
    assert pending_tool is not None
    sink = MagicMock()
    sink.clear_human_request = AsyncMock()
    with patch("app.core.hitl.orchestrator.get_activity_sink", return_value=sink):
        normalized, claimed = await HITLOrchestrator.handle_resume(
            "t-1", pending_tool, "yes"
        )
    assert normalized == "APPROVED"
    assert claimed is True

    async with _hitl_db() as session:
        rows = (await session.execute(select(HumanRequest))).scalars().all()
        by_id = {r.id: r for r in rows}
        # 被批准的那条双轨完成（result=APPROVED），兄弟条合并关闭（status 完成）
        approved_id = pending_tool["request_id"]
        assert by_id[approved_id].status == "completed"
        assert by_id[approved_id].result == "APPROVED"
        for rid, row in by_id.items():
            assert row.status == "completed", f"pending 残留: {rid}"
        msgs = (
            (await session.execute(select(Message).filter_by(thread_id="t-1")))
            .scalars()
            .all()
        )
        assert msgs and all(m.status == "completed" for m in msgs)


# ============ 模型契约（防列漂移） ============


def test_human_request_model_has_authorization_columns():
    """终态契约：human_requests 模型必须带结构化资源锚点三列。"""
    from app.models.conversation import HumanRequest

    cols = {c.name for c in HumanRequest.__table__.columns}
    assert {"resource_path", "resource_action", "expires_at"} <= cols
