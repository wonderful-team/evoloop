"""Unit tests for duty channel (customer-service duty)."""

import pytest

from app.core.channel.base import IncomingMessage
from app.core.channel.duty import (
    ContactDelta,
    DutyChannel,
    RawInbound,
)


class _MockDispatchResult:
    def __init__(self, inputs=None):
        self.inputs = inputs


class _MockDutyChannel(DutyChannel):
    name = "mock_duty"

    def __init__(self, deltas, dispatch_inputs=None):
        super().__init__()
        self._deltas = deltas
        self._dispatch_inputs = dispatch_inputs
        self.dispatched: list[IncomingMessage] = []
        self.replies: list[tuple[str, str]] = []

    async def _scan_contacts(self):
        # 取一条回一条：每次只返回第一个有新增的联系人，取完即空
        if not self._deltas:
            return []
        return [self._deltas.pop(0)]

    async def _to_incoming(self, raw):
        return IncomingMessage(
            source=self.name,
            thread_id="",
            text=raw.text,
            metadata={"contact": raw.contact},
        )

    async def _send_reply(self, contact, text):
        self.replies.append((contact, text))
        return True

    async def _generate_reply(self, contact, raw_texts):
        self.dispatched.append((contact, list(raw_texts)))
        return f"回复{contact}"

    async def _dispatch_safely(self, delta, project_id):
        contact = delta.contact
        reply_text = await self._generate_reply(contact, [r.text for r in delta.raws])
        await self._send_reply(contact, reply_text)

    async def dispatch(self, msg):  # 覆盖 InputChannel.dispatch，避免真实 DB
        self.dispatched.append(msg)
        return _MockDispatchResult(inputs=self._dispatch_inputs)


def test_thread_for_isolates_contacts():
    t1 = DutyChannel._thread_for(120, "客户A")
    t2 = DutyChannel._thread_for(120, "客户B")
    assert t1 != t2
    assert t1 == "duty_120_客户A"


async def test_poll_once_batches_by_contact():
    channel = _MockDutyChannel(
        [
            ContactDelta(
                contact="客户A",
                raws=[
                    RawInbound(contact="客户A", text="你好"),
                    RawInbound(contact="客户A", text="在吗"),
                ],
            ),
        ]
    )
    handled = await channel.poll_once(project_id=120)

    assert handled == 2
    # 按联系人统一回复：两条消息一次生成一条回复
    assert channel.dispatched[0][0] == "客户A"
    assert channel.dispatched[0][1] == ["你好", "在吗"]
    assert channel.replies == [("客户A", "回复客户A")]


async def test_poll_once_handles_multiple_contacts():
    channel = _MockDutyChannel(
        [
            ContactDelta(
                contact="客户A", raws=[RawInbound(contact="客户A", text="你好")]
            ),
            ContactDelta(
                contact="客户B", raws=[RawInbound(contact="客户B", text="在吗")]
            ),
        ]
    )
    handled = await channel.poll_once(project_id=120)

    assert handled == 2
    assert [d[0] for d in channel.dispatched] == ["客户A", "客户B"]


async def test_poll_once_fast_path_no_new():
    channel = _MockDutyChannel([])
    handled = await channel.poll_once(project_id=120)
    assert handled == 0
    assert channel.dispatched == []


async def test_receive_not_supported():
    channel = _MockDutyChannel([])
    with pytest.raises(NotImplementedError):
        await channel.receive({"raw": "x"})
