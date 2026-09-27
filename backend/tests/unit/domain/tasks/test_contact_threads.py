"""联系人固定线程（会话连续性）+ 采集兜底（poll）测试。"""

from __future__ import annotations

import json as _json
from types import SimpleNamespace

from app.models.project import ProjectTask  # noqa: F401
from app.utils.time import utcnow


def _patch_engine(monkeypatch, captured: dict, tmp_path):
    """与 TestDispatcher 同款：stub 引擎，任务 take 语义保真。"""
    from app.core.engine.dispatch import DispatchStatus

    async def _fake_dispatch(**kwargs):
        captured.setdefault("dispatches", []).append(kwargs)
        return SimpleNamespace(
            status=DispatchStatus.QUEUED, inputs={"messages": []}, error=None
        )

    async def _fake_run(thread_id, _inputs):
        from app.domain.tasks.service import TaskQueueService

        captured.setdefault("ran", []).append(thread_id)
        task_id = captured["dispatches"][-1]["metadata"]["source_task_id"]
        await TaskQueueService.take_task(task_id, thread_id)

    monkeypatch.setattr(
        "app.core.engine.dispatch.dispatch_agent_run", _fake_dispatch
    )
    monkeypatch.setattr(
        "app.core.engine.agent.run_agent_background", _fake_run
    )
    monkeypatch.setattr(
        "app.core.engine.capability_profiles.list_domains", lambda _: []
    )
    proj_dir = tmp_path / "project-1"
    (proj_dir / ".evoloop").mkdir(parents=True)
    (proj_dir / ".evoloop" / "project.json").write_text(
        _json.dumps({"customer_service_duty": {"enabled": True}})
    )

    async def _fake_gpp(*_a, **_k):
        return str(proj_dir)

    monkeypatch.setattr("app.core.project.utils.get_project_path", _fake_gpp)
    monkeypatch.setattr(
        "app.core.channel.duty.config.get_project_path", _fake_gpp
    )


async def _mk_external_task(source_ref: dict, dedup: str):
    from app.domain.tasks.service import TaskQueueService

    t = await TaskQueueService.create_task(
        project_id=1,
        title="客户消息",
        source="external",
        source_ref=source_ref,
        dedup_key=dedup,
    )
    # external fail-closed：模拟用户确认提案后入列
    await TaskQueueService.advance_task(t.id, "pending", by="user")
    return t


class TestContactThreadContinuity:
    """方案 a：同一联系人固定线程 wakeup_{pid}_{contact}（历史跨任务累积）。"""

    async def test_same_contact_same_stable_thread(
        self, _db, duty_enabled, monkeypatch, tmp_path
    ):

        from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

        captured: dict = {}
        _patch_engine(monkeypatch, captured, tmp_path)

        await _mk_external_task(
            {
                "kind": "event",
                "source_system": "mall",
                "event_id": "e-1",
                "contact": "wxid_abc",
                "channel": "mcp_message",
            },
            "mall:e-1",
        )
        await dispatch_due_tasks()
        first_threads = list(captured["ran"])

        await _mk_external_task(
            {
                "kind": "event",
                "source_system": "mall",
                "event_id": "e-2",
                "contact": "wxid_abc",
                "channel": "mcp_message",
            },
            "mall:e-2",
        )
        await dispatch_due_tasks()
        all_threads = first_threads + captured["ran"][len(first_threads):]

        assert len(all_threads) == 2
        # 固定线程：无 epoch 后缀，两任务完全同线程 → 历史累积
        assert all_threads[0] == "wakeup_1_wxid_abc"
        assert all_threads[1] == all_threads[0]

    async def test_different_contacts_different_threads(
        self, _db, duty_enabled, monkeypatch, tmp_path
    ):
        from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

        captured: dict = {}
        _patch_engine(monkeypatch, captured, tmp_path)

        for i, contact in enumerate(["wxid_a", "wxid_b"]):
            await _mk_external_task(
                {
                    "kind": "event",
                    "source_system": "mall",
                    "event_id": f"e-{i}",
                    "contact": contact,
                    "channel": "mcp_message",
                },
                f"mall:e-{i}",
            )
        await dispatch_due_tasks()
        assert set(captured["ran"]) == {"wakeup_1_wxid_a", "wakeup_1_wxid_b"}

    async def test_non_contact_task_unique_thread(
        self, _db, duty_enabled, monkeypatch, tmp_path
    ):
        from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

        captured: dict = {}
        _patch_engine(monkeypatch, captured, tmp_path)

        await _mk_external_task(
            {"kind": "event", "source_system": "mall", "event_id": "e-9"},
            "mall:e-9",
        )
        await dispatch_due_tasks()
        assert len(captured["ran"]) == 1
        thread = captured["ran"][0]
        assert thread.startswith("wakeup_1_")
        assert thread != "wakeup_1_wxid_abc"  # 纯工作项走唯一线程

    async def test_channel_name_flows_to_metadata(
        self, _db, duty_enabled, monkeypatch, tmp_path
    ):
        from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

        captured: dict = {}
        _patch_engine(monkeypatch, captured, tmp_path)

        await _mk_external_task(
            {
                "kind": "event",
                "source_system": "mall",
                "event_id": "e-3",
                "contact": "wxid_abc",
                "channel": "mcp_message",
            },
            "mall:e-3",
        )
        await dispatch_due_tasks()
        assert captured["dispatches"][0]["metadata"]["channel_name"] == "mcp_message"


class TestReplyChunking:
    """超长回复分块（MAX_MESSAGE_LEN）。"""

    async def test_long_reply_chunked(self, monkeypatch):
        from app.core.channel.input.mcp_message import (
            MAX_MESSAGE_LEN,
            mcp_message_channel,
        )
        from app.core.events.registry import OutboundReplyEvent

        calls: list[dict] = []
        tool = SimpleNamespace(name="mcp__capability_matrix__mcp_message_reply")

        async def _func(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(text=_json.dumps({"success": True}))]
            )

        tool.func = _func

        import app.core.mcp.client.manager as mgr_module

        class _FakeManager:
            async def get_tools(self, server_name=None):
                return [tool]

        monkeypatch.setattr(mgr_module, "mcp_client_manager", _FakeManager())
        monkeypatch.setattr(
            "app.core.channel.input.mcp_message.REPLY_CHUNK_DELAY_SECONDS", 0.0
        )

        content = "x" * (MAX_MESSAGE_LEN * 2 + 10)
        await mcp_message_channel.on_outbound_reply(
            OutboundReplyEvent(
                channel="mcp_message",
                recipient="wxid_abc",
                content=content,
                project_id=1,
                source_system="capability-matrix",
            )
        )
        assert len(calls) == 3
        assert all(len(c["content"]) <= MAX_MESSAGE_LEN for c in calls)
        assert "".join(c["content"] for c in calls) == content


class TestNonDutyResidueDefense:
    """dispatch_task 对非值守残留行：跳过 + 不推进 next_run_at（防御性）。"""

    async def test_non_duty_row_skipped_without_advance(self, _db):
        from datetime import timedelta

        from sqlalchemy import select

        from app.infrastructure.database import session_scope
        from app.infrastructure.scheduler.service import SchedulerService
        from app.models.scheduler import AutonomousTask

        # tasks conftest 默认不建 autonomous_tasks 表，测试内自建
        async with session_scope() as session:
            await session.run_sync(
                lambda sess: AutonomousTask.__table__.create(
                    sess.get_bind(), checkfirst=True
                )
            )
        async with session_scope() as session:
            row = AutonomousTask(
                intent_description="legacy residue",
                project_id=1,
                trigger_spec="interval:60",
                is_active=True,
                next_run_at=utcnow() - timedelta(minutes=1),
            )
            session.add(row)
            await session.flush()
            row_id, before = row.id, row.next_run_at

        await SchedulerService.dispatch_task(row_id)  # 不抛异常

        async with session_scope() as session:
            row = (
                (await session.execute(select(AutonomousTask).where(AutonomousTask.id == row_id)))
                .scalars()
                .one()
            )
            # sqlite 回读 naive datetime，归一后比较（in-memory aware → naive）
            before_naive = before.replace(tzinfo=None) if before.tzinfo else before
            assert row.next_run_at == before_naive  # 未推进
