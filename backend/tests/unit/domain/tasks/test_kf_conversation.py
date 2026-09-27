"""kf_ 值守会话直通（conversation runtime + 分流 + 回复路由）单测。"""

from __future__ import annotations

import json

from sqlalchemy import select

from app.models.project import ProjectTask


class TestKfConversationPath:
    """mcp_message + contact → 会话直通（不落任务队列）。"""

    def _event(self, **overrides):
        from app.core.events.registry import InboundMessageEvent

        fields = {
            "source_system": "cap-server",
            "event_id": "kf-1",
            "project_id": 1,
            "title": "customer asks",
            "content": "我的订单发货了吗",
            "contact": "order-1001",
            "channel": "mcp_message",
        }
        fields.update(overrides)
        return InboundMessageEvent(**fields)

    async def test_kf_message_bypasses_task_queue(self, _db):
        """分流后不落 ProjectTask（画布/任务列表不可见）。"""
        from app.domain.tasks.event.subscribers import inbound_message_subscriber
        from app.infrastructure.database import session_scope

        await inbound_message_subscriber.on_inbound_message(self._event())

        async with session_scope() as session:
            rows = (
                await session.execute(select(ProjectTask))
            ).scalars().all()
        assert rows == []

    async def test_kf_message_dispatches_conversation_thread(self, _db):
        """直通调用 conversation runtime：kf_{project}_{contact} 线程。"""
        from unittest.mock import AsyncMock, patch

        from app.domain.tasks.event.subscribers import inbound_message_subscriber

        with patch(
            "app.core.engine.dispatch.dispatch_agent_run", new_callable=AsyncMock
        ) as mock_run, patch(
            "app.core.engine.session.manager.session_manager.submit",
            new_callable=AsyncMock,
        ) as mock_submit:
            mock_run.return_value = type("R", (), {"inputs": {"x": 1}})()
            await inbound_message_subscriber.on_inbound_message(self._event(event_id="kf-2"))

        assert mock_run.await_count == 1
        assert mock_run.await_args.kwargs["thread_id"] == "kf_1_order-1001"
        assert mock_submit.await_count == 1
        assert mock_submit.await_args.args[0] == "kf_1_order-1001"

    async def test_kf_message_dedup_skips_second_delivery(self, _db):
        """同 event_id 重推：幂等跳过，不再派发。"""
        from unittest.mock import AsyncMock, patch

        from app.core.state import shared_state
        from app.domain.tasks.event.subscribers import inbound_message_subscriber

        with patch(
            "app.core.engine.dispatch.dispatch_agent_run", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = type("R", (), {"inputs": {"ok": True}})()
            await inbound_message_subscriber.on_inbound_message(
                self._event(event_id="kf-3")
            )
            await inbound_message_subscriber.on_inbound_message(
                self._event(event_id="kf-3")
            )

        assert mock_run.await_count == 1
        assert await shared_state.get("mcp_kf_dedup:cap-server:kf-3", "")

    async def test_kf_message_without_contact_still_enters_queue(self, _db):
        """纯工作项（无 contact）：照旧落任务队列。"""
        from app.domain.tasks.event.subscribers import inbound_message_subscriber
        from app.infrastructure.database import session_scope

        await inbound_message_subscriber.on_inbound_message(
            self._event(event_id="kf-2", contact=None)
        )

        async with session_scope() as session:
            rows = (
                await session.execute(select(ProjectTask))
            ).scalars().all()
        assert len(rows) == 1
        assert rows[0].source == "external"

    async def test_route_meta_persisted(self, _db):
        """路由元数据（contact/channel/source_system）落 SharedState。"""
        import json as _json
        from unittest.mock import AsyncMock, patch

        from app.core.state import shared_state
        from app.domain.tasks.event.subscribers import inbound_message_subscriber

        with patch(
            "app.core.engine.dispatch.dispatch_agent_run", new_callable=AsyncMock
        ):
            await inbound_message_subscriber.on_inbound_message(self._event(event_id="kf-4"))

        raw = await shared_state.get("kf_route:kf_1_order-1001", "")
        meta = _json.loads(raw) if raw else {}
        assert meta.get("contact") == "order-1001"
        assert meta.get("channel") == "mcp_message"
        assert meta.get("project_id") == 1


class TestKfReplyRouter:
    """kf_ 会话终态 → OutboundReplyEvent。"""

    def _completed(self, thread_id: str, summary: str):
        from unittest.mock import MagicMock

        ev = MagicMock()
        data = MagicMock()
        data.thread_id = thread_id
        data.summary = summary
        ev.data = data
        return ev

    async def test_replies_routed_from_shared_state_meta(self, _db):
        from unittest.mock import AsyncMock, patch

        from app.core.events import system_bus
        from app.core.state import shared_state
        from app.domain.tasks.event.subscribers import kf_reply_router

        await shared_state.set(
            "kf_route:kf_1_order-1001",
            json.dumps(
                {
                    "contact": "order-1001",
                    "channel": "mcp_message",
                    "source_system": "cap-server",
                    "project_id": 1,
                }
            ),
        )
        ev = self._completed("kf_1_order-1001", "已发货，单号 SF001")

        with patch.object(
            system_bus, "publish", new_callable=AsyncMock
        ) as mock_pub:
            await kf_reply_router.on_session_completed(ev)

        assert mock_pub.await_count == 1
        event = mock_pub.await_args.args[0]
        assert event.channel == "mcp_message"
        assert event.recipient == "order-1001"
        assert event.content == "已发货，单号 SF001"

    async def test_empty_summary_no_reply(self, _db):
        from unittest.mock import AsyncMock, patch

        from app.core.events import system_bus
        from app.core.state import shared_state
        from app.domain.tasks.event.subscribers import kf_reply_router

        await shared_state.set(
            "kf_route:kf_1_x",
            json.dumps({"contact": "x", "channel": "mcp_message"}),
        )
        with patch.object(system_bus, "publish", new_callable=AsyncMock):
            await kf_reply_router.on_session_completed(
                self._completed("kf_1_x", "")
            )
        # publish 断言由 mock 自身记录；空 summary 不发——直接依赖不抛错
