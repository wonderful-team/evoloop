"""全链路贯通测试：mcp_message 通知 → 建任务 → 派发（联系人线程）→
会话完成 → 回复路由 → mcp_message_reply 工具调用。

仅 stub 两处：引擎 run（run_agent_background）与 MCP 传输（mcp_client_manager）。
事件总线、channel 归一化、domain 摄取/路由、dispatcher 全部走真实组件与真实订阅。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

# 导入即完成订阅注册（channel 单例 + domain 订阅者）
import app.core.channel  # noqa: F401
import app.domain.tasks  # noqa: F401
import app.models.planning  # noqa: F401
import app.models.project  # noqa: F401
from app.models.project import ProjectTask


def _notification(params: dict):
    """manager.py 发布的真实 MCP 通知事件（notifications/message wrapper，
    消息本体在 data.payload.data，data.type=mcp_message_send）。"""
    from app.core.events.base import BaseEvent, EventData
    from app.core.events.registry import SystemEventType

    class _McpServerNotificationEvent(BaseEvent):
        event_type: str = SystemEventType.MCP_SERVER_NOTIFICATION
        server_name: str
        method: str | None

    method = "notifications/message"
    return _McpServerNotificationEvent(
        server_name="capability-matrix-online",
        method=method,
        data=EventData.model_validate(
            {
                "method": method,
                "payload": {
                    "level": "info",
                    "logger": "mcp_message",
                    "data": {"type": "mcp_message_send", **params},
                },
            }
        ),
    )


def _patch_engine(monkeypatch, captured: dict, tmp_path):
    from app.core.engine.dispatch import DispatchStatus

    async def _fake_dispatch(**kwargs):
        captured.setdefault("dispatches", []).append(kwargs)
        return SimpleNamespace(
            status=DispatchStatus.QUEUED, inputs={"messages": []}, error=None
        )

    async def _fake_run(thread_id, _inputs):
        from app.domain.tasks.service import TaskQueueService

        captured.setdefault("ran", []).append(thread_id)
        # 任务车道 run 带 source_task_id（take 认领）；kf 会话直通无任务
        task_id = (captured["dispatches"][-1].get("metadata") or {}).get(
            "source_task_id"
        )
        if task_id:
            await TaskQueueService.take_task(task_id, thread_id)

    monkeypatch.setattr(
        "app.core.engine.dispatch.dispatch_agent_run", _fake_dispatch
    )
    monkeypatch.setattr(
        "app.core.engine.agent.run_agent_background", _fake_run
    )

    # kf 会话直通走 session_manager（真实引擎 loop 需要全套内存表）——
    # e2e 只关心线程与提交语义，get_or_create stub 成记录型假会话。
    class _FakeSession:
        def inject_user_message(self, _inputs):
            pass

    async def _fake_get_or_create(thread_id):
        captured.setdefault("sessions", []).append(thread_id)
        return _FakeSession()

    monkeypatch.setattr(
        "app.core.engine.session.manager.session_manager.get_or_create",
        _fake_get_or_create,
    )
    monkeypatch.setattr(
        "app.core.engine.capability_profiles.list_domains", lambda _: []
    )
    proj_dir = tmp_path / "project-1"
    (proj_dir / ".evoloop").mkdir(parents=True)
    (proj_dir / ".evoloop" / "project.json").write_text(
        json.dumps({"customer_service_duty": {"enabled": True}})
    )

    async def _fake_gpp(*_a, **_k):
        return str(proj_dir)

    monkeypatch.setattr("app.core.project.utils.get_project_path", _fake_gpp)
    monkeypatch.setattr(
        "app.core.channel.duty.config.get_project_path", _fake_gpp
    )


def _patch_reply_tool(monkeypatch) -> list[dict]:
    import app.core.mcp.client.manager as mgr_module

    tool = SimpleNamespace(name="mcp__capability_matrix_online__mcp_message_reply")
    calls: list[dict] = []

    async def _func(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps({"success": True}))]
        )

    tool.func = _func

    class _FakeManager:
        async def get_tools(self, server_name=None):
            return [tool]

    monkeypatch.setattr(mgr_module, "mcp_client_manager", _FakeManager())
    monkeypatch.setattr(
        "app.core.channel.input.mcp_message.REPLY_CHUNK_DELAY_SECONDS", 0.0
    )
    return calls


async def _publish_session_completed(thread_id: str, summary: str) -> None:
    from app.core.events import system_bus
    from app.core.events.schemas.lifecycle import (
        SessionCompletedData,
        SessionCompletedEvent,
    )

    await system_bus.publish(
        SessionCompletedEvent(
            data=SessionCompletedData(thread_id=thread_id, summary=summary)
        )
    )


@pytest.mark.timeout(30)
async def test_full_pipeline_notification_to_reply(
    _db, monkeypatch, tmp_path
):
    """kf_ 会话直通 e2e：客服通知 → 直派会话线程（不落任务）→ 完成回复。"""

    from sqlalchemy import select

    from app.core.events import system_bus
    from app.infrastructure.database import session_scope

    captured: dict = {}
    _patch_engine(monkeypatch, captured, tmp_path)
    reply_calls = _patch_reply_tool(monkeypatch)

    # 1) 第三方推送 mcp_message（真实总线，真实 ingress 订阅者归一化 + 分流）
    await system_bus.publish(
        _notification(
            {
                "event_id": "evt-100",
                "title": "客户咨询发货",
                "content": "订单 #123 什么时候发？",
                "project_id": 1,
                "contact": "wxid_abc",
            }
        )
    )

    # 摄取已发生：会话类消息不落任务队列（画布/任务列表不可见）

    async with session_scope() as session:
        rows = (
            (await session.execute(select(ProjectTask))).scalars().all()
        )
    assert rows == []

    # 2) 会话直通：kf_{project}_{contact} 固定线程（await_completion=False）
    assert captured["sessions"] == ["kf_1_wxid_abc"]
    assert captured["dispatches"][0]["thread_id"] == "kf_1_wxid_abc"
    assert captured["dispatches"][0]["metadata"]["contact"] == "wxid_abc"
    assert captured["dispatches"][0]["metadata"]["channel_name"] == "mcp_message"

    # 3) 会话成功完成（真实 SessionCompletedEvent → KfReplyRouter）
    await _publish_session_completed("kf_1_wxid_abc", "今天下午发货，单号 SF123")

    # 4) 回复经 OutboundReplyEvent 路由到渠道 → mcp_message_reply 工具
    assert len(reply_calls) == 1
    assert reply_calls[0]["contact"] == "wxid_abc"
    assert reply_calls[0]["content"] == "今天下午发货，单号 SF123"
    assert reply_calls[0]["project_id"] == 1


@pytest.mark.timeout(30)
async def test_full_pipeline_no_contact_never_replies(
    _db, monkeypatch, tmp_path
):
    """纯工作项（无 contact）：任务正常派发，完成零回复。"""
    from app.core.events import system_bus
    from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

    captured: dict = {}
    _patch_engine(monkeypatch, captured, tmp_path)
    reply_calls = _patch_reply_tool(monkeypatch)

    await system_bus.publish(
        _notification(
            {
                "event_id": "evt-200",
                "title": "库存巡检",
                "content": "检查今日库存快照",
                "project_id": 1,
            }
        )
    )
    # external fail-closed：确认提案后入列
    from app.domain.tasks.service import TaskQueueService

    external_task = await TaskQueueService.get_by_dedup_key(
        "capability-matrix-online:evt-200"
    )
    assert external_task is not None
    await TaskQueueService.advance_task(external_task.id, "pending", by="user")
    await dispatch_due_tasks()
    assert len(captured["ran"]) == 1
    assert not captured["ran"][0].startswith("wakeup_1_wxid_")  # 非联系人线程

    await _publish_session_completed(captured["ran"][0], "巡检完成")
    assert reply_calls == []
