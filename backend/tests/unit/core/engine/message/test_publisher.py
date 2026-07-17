"""Publisher + Channel tests: publish() dispatch via ChannelRegistry, WebChannel, MobileChannel."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel import (
    Channel,
    ChannelContext,
    ChannelRegistry,
    WebChannel,
    MobileChannel,
)
from app.core.engine.message.publisher import MessagePublisher


class _TestChannel(Channel):
    """Minimal Channel impl for testing dispatch routing."""

    def __init__(self, name="test", accepts_blocks=True, accepts_stream_events=True):
        self.name = name
        self.accepts_blocks = accepts_blocks
        self.accepts_stream_events = accepts_stream_events
        self._send_mock = AsyncMock()
        self._custom_mock = AsyncMock()
        self._hitl_mock = AsyncMock()

    async def send(self, payload, ctx):
        await self._send_mock(payload, ctx)

    async def send_custom_event(self, event_type, data, ctx):
        await self._custom_mock(event_type, data, ctx)

    async def send_hitl_request(self, request_id, request_type, prompt, ctx, **kwargs):
        await self._hitl_mock(request_id, request_type, prompt, ctx, **kwargs)


@pytest.fixture
def publisher():
    return MessagePublisher(thread_id="test-thread")


@pytest.fixture
def real_msg_block():
    """Real MessageBlock instance for isinstance checks in publish()."""
    from app.core.engine.message.schemas import MessageBlock
    return MessageBlock(
        id="msg-1",
        thread_id="test-thread",
        role="human",
        content="hello",
        sequence_number=1,
        created_at="2024-01-15T10:00:00Z",
    )


@pytest.fixture
def real_stream_event():
    """Real BaseStreamEvent for publish() channel routing tests."""
    from app.models.schemas.events import BaseStreamEvent
    class FakeEvent(BaseStreamEvent):
        type: str = "test_event"
    return FakeEvent(thread_id="test-thread")


# =============================================================================
# Registry tests
# =============================================================================

class TestChannelRegistry:
    """ChannelRegistry — registration and selection logic."""

    def test_register_and_get(self):
        reg = ChannelRegistry()
        ch = WebChannel()
        reg.register(ch)
        assert reg.get("sse") is ch
        assert reg.has("sse")
        assert "sse" in reg.names()

    def test_unregister(self):
        reg = ChannelRegistry()
        reg.register(WebChannel())
        removed = reg.unregister("sse")
        assert removed is not None
        assert not reg.has("sse")

    def test_select_by_name(self):
        reg = ChannelRegistry()
        reg.register(WebChannel())
        reg.register(MobileChannel())
        selected = reg.select({"mobile"}, payload_is_block=True)
        assert len(selected) == 1
        assert selected[0].name == "mobile"

    def test_select_filters_by_payload_type(self):
        reg = ChannelRegistry()
        reg.register(WebChannel())      # accepts_stream_events=True
        reg.register(MobileChannel())   # accepts_stream_events=False
        # Stream events should only go to WebChannel
        selected = reg.select(None, payload_is_block=False)
        assert len(selected) == 1
        assert selected[0].name == "sse"

    def test_select_none_names_selects_all_compatible(self):
        reg = ChannelRegistry()
        reg.register(WebChannel())
        reg.register(MobileChannel())
        selected = reg.select(None, payload_is_block=True)
        assert len(selected) == 2

    def test_select_empty_set_selects_none(self):
        reg = ChannelRegistry()
        reg.register(WebChannel())
        reg.register(MobileChannel())
        selected = reg.select(set(), payload_is_block=True)
        assert len(selected) == 0


# =============================================================================
# Publisher dispatch tests (via mock channels)
# =============================================================================

class TestPublishEntryPoint:
    """publish() — main entry: dispatches to registered channels."""

    @pytest.mark.asyncio
    async def test_message_block_dispatches_to_registered_channels(self, publisher, real_msg_block):
        """MessageBlock dispatches to all channels that accept blocks."""
        mock_ch = _TestChannel(name="mock", accepts_blocks=True, accepts_stream_events=False)

        reg = ChannelRegistry()
        reg.register(mock_ch)

        with patch("app.core.engine.message.publisher.channel_registry", reg):
            await publisher.publish(real_msg_block, channels={"mock"})

        mock_ch._send_mock.assert_awaited_once()
        args = mock_ch._send_mock.call_args[0]
        assert args[0] is real_msg_block
        assert isinstance(args[1], ChannelContext)
        assert args[1].thread_id == "test-thread"

    @pytest.mark.asyncio
    async def test_stream_event_only_goes_to_stream_channels(self, publisher, real_stream_event):
        """BaseStreamEvent only goes to channels with accepts_stream_events=True."""
        mock_stream = _TestChannel(name="stream_ch", accepts_blocks=False, accepts_stream_events=True)
        mock_block_only = _TestChannel(name="block_ch", accepts_blocks=True, accepts_stream_events=False)

        reg = ChannelRegistry()
        reg.register(mock_stream)
        reg.register(mock_block_only)

        with patch("app.core.engine.message.publisher.channel_registry", reg):
            await publisher.publish(real_stream_event, channels={"stream_ch"})

        mock_stream._send_mock.assert_awaited_once()
        mock_block_only._send_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_custom_channels_filters_selection(self, publisher, real_msg_block):
        """channels parameter filters which channels receive the payload."""
        mock_a = AsyncMock(spec=Channel)
        mock_a.name = "a"
        mock_a.accepts_blocks = True
        mock_a.accepts_stream_events = True

        mock_b = AsyncMock(spec=Channel)
        mock_b.name = "b"
        mock_b.accepts_blocks = True
        mock_b.accepts_stream_events = True

        reg = ChannelRegistry()
        reg.register(mock_a)
        reg.register(mock_b)

        with patch("app.core.engine.message.publisher.channel_registry", reg):
            await publisher.publish(real_msg_block, channels={"a"})

            mock_a.send.assert_awaited_once()
            mock_b.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_channels_skips_all(self, publisher, real_msg_block):
        """channels=set() dispatches to nothing."""
        mock_ch = AsyncMock(spec=Channel)
        mock_ch.name = "mock"
        mock_ch.accepts_blocks = True

        reg = ChannelRegistry()
        reg.register(mock_ch)

        with patch("app.core.engine.message.publisher.channel_registry", reg):
            await publisher.publish(real_msg_block, channels=set())

            mock_ch.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_action_passed_in_context(self, publisher, real_msg_block):
        """action parameter is passed through ChannelContext."""
        mock_ch = _TestChannel(name="mock", accepts_blocks=True)

        reg = ChannelRegistry()
        reg.register(mock_ch)

        with patch("app.core.engine.message.publisher.channel_registry", reg):
            await publisher.publish(real_msg_block, channels={"mock"}, action="update")

        ctx = mock_ch._send_mock.call_args[0][1]
        assert ctx.action == "update"


# =============================================================================
# WebChannel tests
# =============================================================================

class TestWebChannel:
    """WebChannel — SSE transport via MessageBroker."""

    @pytest.mark.asyncio
    async def test_sse_serializes_message_block(self, real_msg_block):
        """MessageBlock is serialized via BlockMapper.to_sse and published to MessageBroker."""
        ch = WebChannel()
        with (
            patch("app.core.channel.web_channel.BlockMapper") as mock_mapper,
            patch("app.core.channel.web_channel.get_message_broker") as mock_get_broker,
        ):
            mock_event = MagicMock()
            mock_event.model_dump_json.return_value = '{"type":"block_event"}'
            mock_mapper.to_sse.return_value = mock_event
            mock_broker = AsyncMock()
            mock_get_broker.return_value = mock_broker

            ctx = ChannelContext(thread_id="test-thread", action="create")
            await ch.send(real_msg_block, ctx)

            mock_mapper.to_sse.assert_called_once_with(real_msg_block, action="create")
            mock_broker.publish.assert_awaited_once_with(
                "chat:test-thread:events",
                '{"type":"block_event"}',
            )

    @pytest.mark.asyncio
    async def test_sse_serializes_stream_event(self, real_stream_event):
        """BaseStreamEvent is serialized via to_json()."""
        ch = WebChannel()
        with patch("app.core.channel.web_channel.get_message_broker") as mock_get_broker:
            mock_broker = AsyncMock()
            mock_get_broker.return_value = mock_broker

            ctx = ChannelContext(thread_id="test-thread")
            await ch.send(real_stream_event, ctx)

            mock_broker.publish.assert_awaited_once()
            args = mock_broker.publish.call_args[0]
            assert args[0] == "chat:test-thread:events"
            assert '"type":"test_event"' in args[1]



# =============================================================================
# MobileChannel tests
# =============================================================================

class TestMobileChannelHueyFallback:
    """MobileChannel — WS priority, Huey HTTP fallback."""

    @pytest.mark.asyncio
    async def test_ws_ok_skips_huey(self):
        """WS send success -> no Huey fallback."""
        from app.core.engine.message.schemas import MessageBlock
        block = MessageBlock(
            id="msg-1", thread_id="t", role="human", content="hi",
            sequence_number=1, created_at="2024-01-15T10:00:00Z",
        )

        ch = MobileChannel()
        with (
            patch("app.core.channel.mobile_channel.evocloud_manager") as mock_mgr,
            patch("app.core.channel.mobile_channel.BlockMapper") as mock_mapper,
            patch("app.core.channel.mobile_channel.settings") as mock_settings,
        ):
            mock_settings.MOBILE_SYNC_ENABLED = True
            mock_mgr.api = AsyncMock()
            mock_mgr.api.request = AsyncMock(return_value={"code": 0})
            mock_mapper.to_mobile.return_value = {"role": "human", "content": "hello"}

            with patch("app.core.engine.message.tasks.mobile_sync_http_task") as mock_task:
                ctx = ChannelContext(thread_id="test-thread")
                await ch.send(block, ctx)

                mock_mgr.api.request.assert_awaited_once()
                mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_ws_disconnected_enqueues_huey(self):
        """WS not connected -> enqueue Huey fallback."""
        from app.core.engine.message.schemas import MessageBlock
        block = MessageBlock(
            id="msg-1", thread_id="t", role="human", content="hi",
            sequence_number=1, created_at="2024-01-15T10:00:00Z",
        )

        ch = MobileChannel()
        with (
            patch("app.core.channel.mobile_channel.evocloud_manager") as mock_mgr,
            patch("app.core.channel.mobile_channel.BlockMapper") as mock_mapper,
            patch("app.core.channel.mobile_channel.settings") as mock_settings,
        ):
            mock_settings.MOBILE_SYNC_ENABLED = True
            mock_mgr.api = AsyncMock()
            mock_mgr.api.request = AsyncMock(side_effect=ConnectionError("WS disconnected"))
            mock_mapper.to_mobile.return_value = {"role": "human", "content": "hello"}

            with patch("app.core.engine.message.tasks.mobile_sync_http_task") as mock_task:
                ctx = ChannelContext(thread_id="test-thread")
                await ch.send(block, ctx)

                mock_mgr.api.request.assert_awaited_once()
                mock_task.delay.assert_called_once_with({"role": "human", "content": "hello"})

    @pytest.mark.asyncio
    async def test_ws_raises_enqueues_huey(self):
        """WS send raises -> enqueue Huey fallback."""
        from app.core.engine.message.schemas import MessageBlock
        block = MessageBlock(
            id="msg-1", thread_id="t", role="human", content="hi",
            sequence_number=1, created_at="2024-01-15T10:00:00Z",
        )

        ch = MobileChannel()
        with (
            patch("app.core.channel.mobile_channel.evocloud_manager") as mock_mgr,
            patch("app.core.channel.mobile_channel.BlockMapper") as mock_mapper,
            patch("app.core.channel.mobile_channel.settings") as mock_settings,
        ):
            mock_settings.MOBILE_SYNC_ENABLED = True
            mock_mgr.api = AsyncMock()
            mock_mgr.api.request = AsyncMock(side_effect=ConnectionError("HTTP send failed"))
            mock_mapper.to_mobile.return_value = {"role": "human", "content": "hello"}

            with patch("app.core.engine.message.tasks.mobile_sync_http_task") as mock_task:
                ctx = ChannelContext(thread_id="test-thread")
                await ch.send(block, ctx)

                mock_mgr.api.request.assert_awaited_once()
                mock_task.delay.assert_called_once_with({"role": "human", "content": "hello"})

    @pytest.mark.asyncio
    async def test_mobile_sync_disabled_skips(self):
        """MOBILE_SYNC_ENABLED=False -> skip everything."""
        from app.core.engine.message.schemas import MessageBlock
        block = MessageBlock(
            id="msg-1", thread_id="t", role="human", content="hi",
            sequence_number=1, created_at="2024-01-15T10:00:00Z",
        )

        ch = MobileChannel()
        with (
            patch("app.core.channel.mobile_channel.settings") as mock_settings,
            patch("app.core.channel.mobile_channel.evocloud_manager") as mock_mgr,
            patch("app.core.channel.mobile_channel.BlockMapper") as mock_mapper,
        ):
            mock_settings.MOBILE_SYNC_ENABLED = False

            with patch("app.core.engine.message.tasks.mobile_sync_http_task") as mock_task:
                ctx = ChannelContext(thread_id="test-thread")
                await ch.send(block, ctx)

                mock_mgr.link.send_message.assert_not_called()
                mock_mapper.to_mobile.assert_not_called()
                mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_human_not_visible_skips(self):
        """Invisible human messages are skipped (loopback guard)."""
        from app.core.engine.message.schemas import MessageBlock
        block = MessageBlock(
            id="msg-1", thread_id="t", role="human", content="hi",
            sequence_number=1, created_at="2024-01-15T10:00:00Z",
            is_visible=False,
        )

        ch = MobileChannel()
        with (
            patch("app.core.channel.mobile_channel.settings") as mock_settings,
            patch("app.core.channel.mobile_channel.evocloud_manager") as mock_mgr,
            patch("app.core.channel.mobile_channel.BlockMapper") as mock_mapper,
        ):
            mock_settings.MOBILE_SYNC_ENABLED = True

            with patch("app.core.engine.message.tasks.mobile_sync_http_task") as mock_task:
                ctx = ChannelContext(thread_id="test-thread")
                await ch.send(block, ctx)

                mock_mgr.link.send_message.assert_not_called()
                mock_mapper.to_mobile.assert_not_called()
                mock_task.delay.assert_not_called()
