"""Shared fixtures: in-memory aiosqlite patched into db_resource_manager."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

import app.models.codebase  # noqa: F401
import app.models.conversation  # noqa: F401
import app.models.planning  # noqa: F401
import app.models.project  # noqa: F401
from app.models.codebase import Repository
from app.models.conversation import (
    AgentActivity,
    Conversation,
    HumanRequest,
    Message,
    MessageReference,
    ThreadSequence,
)
from app.models.planning import Plan, PlanStep
from app.models.project import ProjectTask
from app.models.task_run import TaskRun
from app.models.task_workflow import TaskArtifact, TaskWorkflow


@pytest.fixture
async def _db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    from tests.unit.db_stub import stub_db_for_loop

    factory = stub_db_for_loop(monkeypatch, engine)
    _ = monkeypatch  # noqa: F841 — 保留引用便于断言
    async def _install():
        async with factory() as session:
            await session.run_sync(
                lambda sess: ProjectTask.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Message.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: ThreadSequence.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Conversation.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: AgentActivity.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: HumanRequest.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: TaskWorkflow.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: TaskArtifact.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: TaskRun.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Plan.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: PlanStep.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Repository.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: MessageReference.__table__.create(sess.get_bind(), checkfirst=True)
            )

    async def _install_tables():
        async with factory() as session:
            await session.run_sync(
                lambda sess: ProjectTask.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Message.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: ThreadSequence.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Conversation.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: AgentActivity.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: HumanRequest.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: TaskWorkflow.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: TaskArtifact.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Plan.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: PlanStep.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Repository.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: MessageReference.__table__.create(sess.get_bind(), checkfirst=True)
            )

    await _install()

    try:
        yield factory, engine, monkeypatch
    finally:
        # loop 感知修复（同 mcp conftest 的 runner 治理）：in-memory aiosqlite
        # engine 的 worker 线程绑定本测试 loop；不 dispose 会在 loop 关闭后
        # 报 "Event loop is closed"，被 pytest 归因到无辜的后续测试（合跑漂移）。
        await engine.dispose()


@pytest.fixture(autouse=True)
async def _tables(_db):
    factory, engine, mp = _db
    from app.infrastructure.database import resource_manager

    loop = resource_manager.db_resource_manager._current_loop()
    # 同 tests/unit/db_stub.py：_engines 一并登记，initialize() 才会短路，
    # 不覆写测试注入的 session factory。
    mp.setattr(
        resource_manager.db_resource_manager,
        "_session_factories",
        {loop: factory},
    )
    mp.setattr(resource_manager.db_resource_manager, "_engines", {loop: engine})
    async def _setup():
        async with factory() as session:
            await session.run_sync(
                lambda sess: ProjectTask.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Message.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Conversation.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: AgentActivity.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: HumanRequest.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: TaskWorkflow.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: TaskArtifact.__table__.create(sess.get_bind(), checkfirst=True)
            )
            await session.run_sync(
                lambda sess: Repository.__table__.create(sess.get_bind(), checkfirst=True)
            )
    await _setup()

    yield


@pytest.fixture
async def duty_enabled(monkeypatch):
    """值守开关全开：claim_due_tasks 的 project 级 opt-in 门槛放行。"""

    async def _fake_cfg(_pid):
        return {"enabled": True}

    monkeypatch.setattr(
        "app.core.channel.duty.config.load_duty_config", _fake_cfg
    )
    yield


@pytest.fixture(autouse=True)
async def _global_duty_on(monkeypatch):
    """测试环境默认总闸开：全局守门（托盘停止值守）由 TestGlobalMasterSwitch 专项覆盖。"""

    def _fake_global_cfg():
        return {"enabled": True}

    monkeypatch.setattr(
        "app.core.channel.duty.config.load_global_duty_config", _fake_global_cfg
    )
    yield
