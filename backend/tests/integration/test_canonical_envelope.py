"""
Integration tests for canonical envelope handling in EvoCloudWebSocketLink.

Tests _handle_ws_message processing of canonical messages:
- Non-canonical messages dropped
- command.relay routes through LINK_LAYER_HANDLERS["command.relay"]
- command.stop/retry/rewind and hitl.response/cancel publish via publish_ws_message_received
- system.init/error directly call protocol handlers
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from schemas.generated.python.canonical import MessageType, create_envelope


@pytest.fixture
def mock_link():
    """Create a minimal EvoCloudWebSocketLink instance with all dependencies mocked."""
    from app.core.evocloud.backends.websocket_link import (
        EvoCloudWebSocketLink,
    )

    config = MagicMock()
    config.device_name = "test-device"
    api_client = MagicMock()
    api_client.on_token_change = MagicMock()

    link = EvoCloudWebSocketLink(config, api_client)
    link._device_key = "test-dev-key"
    link._handshake_completed = True
    link._running = True
    link.send_message = AsyncMock()
    yield link


class TestCanonicalEnvelopeHandling:
    """Test _handle_ws_message with canonical envelopes."""

    @pytest.mark.asyncio
    async def test_non_canonical_dropped(self, mock_link):
        """Non-canonical message (no version) should be dropped without handler call."""
        raw_msg = json.dumps({"type": "command.relay", "body": {"action": "chat"}})
        with patch(
            "app.core.engine.event.publishers.publish_ws_message_received",
            new_callable=AsyncMock,
        ) as mock_publish:
            await mock_link._handle_ws_message(raw_msg)
            mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_command_relay_via_link_handler(self, mock_link):
        """command.relay should call LINK_LAYER_HANDLERS['command.relay'] with command_id."""
        env = create_envelope(
            type=MessageType.COMMAND_RELAY,
            body={
                "command_id": 12345,
                "message_id": "msg-uuid",
                "thread_id": "th-1",
                "action": "chat",
                "content": {"text": "hello"},
            },
        )
        raw_msg = json.dumps(env.model_dump())

        relay_mock = AsyncMock(return_value=True)
        mock_link._LINK_LAYER_HANDLERS = {
            "command.relay": relay_mock,
            "system.init": AsyncMock(),
            "system.error": AsyncMock(),
        }

        await mock_link._handle_ws_message(raw_msg)
        relay_mock.assert_awaited_once()
        payload = relay_mock.await_args[0][1]
        assert payload["command_id"] == 12345
        assert payload["action"] == "chat"
        assert payload["thread_id"] == "th-1"

    @pytest.mark.asyncio
    async def test_command_relay_missing_command_id_defaults_zero(self, mock_link):
        """command.relay without command_id defaults to 0 in link-layer handler."""
        payload = {
            "message_id": "msg-uuid",
            "thread_id": "th-1",
            "action": "chat",
            "content": "hello",
        }
        await mock_link._on_command_relay_protocol(payload)
        assert payload["command_id"] == 0
        mock_link.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_command_relay_handler_returns_false_stops(self, mock_link):
        """When LINK_LAYER_HANDLERS returns False, should not continue to publish."""
        env = create_envelope(
            type=MessageType.COMMAND_RELAY,
            body={
                "command_id": 1,
                "message_id": "m1",
                "thread_id": "th-1",
                "action": "chat",
                "content": "x",
            },
        )
        raw_msg = json.dumps(env.model_dump())

        relay_mock = AsyncMock(return_value=False)
        mock_link._LINK_LAYER_HANDLERS = {
            "command.relay": relay_mock,
            "system.init": AsyncMock(),
            "system.error": AsyncMock(),
        }

        with patch(
            "app.core.engine.event.publishers.publish_ws_message_received",
            new_callable=AsyncMock,
        ) as mock_publish:
            await mock_link._handle_ws_message(raw_msg)
            relay_mock.assert_awaited_once()
            mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_command_stop_publishes_action_stop(self, mock_link):
        """command.stop should publish with msg_type='command.stop'."""
        env = create_envelope(
            type=MessageType.COMMAND_STOP,
            body={"command_id": 200, "thread_id": "th-1"},
        )
        raw_msg = json.dumps(env.model_dump())

        with patch(
            "app.core.engine.event.publishers.publish_ws_message_received",
            new_callable=AsyncMock,
        ) as mock_publish:
            await mock_link._handle_ws_message(raw_msg)
            mock_publish.assert_awaited_once()
            args = mock_publish.await_args[1]
            assert args["msg_type"] == "command.stop"
            assert args["payload"]["command_id"] == 200
            assert args["payload"]["thread_id"] == "th-1"

    @pytest.mark.asyncio
    async def test_command_retry_publishes_action_retry(self, mock_link):
        """command.retry should publish with msg_type='command.retry'."""
        env = create_envelope(
            type=MessageType.COMMAND_RETRY,
            body={"command_id": 300, "thread_id": "th-1", "message_id": "m1"},
        )
        raw_msg = json.dumps(env.model_dump())

        with patch(
            "app.core.engine.event.publishers.publish_ws_message_received",
            new_callable=AsyncMock,
        ) as mock_publish:
            await mock_link._handle_ws_message(raw_msg)
            args = mock_publish.await_args[1]
            assert args["msg_type"] == "command.retry"
            assert args["payload"]["command_id"] == 300

    @pytest.mark.asyncio
    async def test_command_rewind_publishes_action_rewind(self, mock_link):
        """command.rewind should publish with msg_type='command.rewind'."""
        env = create_envelope(
            type=MessageType.COMMAND_REWIND,
            body={"command_id": 400, "thread_id": "th-1", "message_id": "m1"},
        )
        raw_msg = json.dumps(env.model_dump())

        with patch(
            "app.core.engine.event.publishers.publish_ws_message_received",
            new_callable=AsyncMock,
        ) as mock_publish:
            await mock_link._handle_ws_message(raw_msg)
            args = mock_publish.await_args[1]
            assert args["msg_type"] == "command.rewind"
            assert args["payload"]["command_id"] == 400

    @pytest.mark.asyncio
    async def test_hitl_response_publishes_hitl_response(self, mock_link):
        """hitl.response should publish with msg_type='hitl.response'."""
        env = create_envelope(
            type=MessageType.HITL_RESPONSE,
            body={
                "command_id": 500,
                "request_id": "req-1",
                "action": "confirm",
                "value": "APPROVED",
            },
        )
        raw_msg = json.dumps(env.model_dump())

        with patch(
            "app.core.engine.event.publishers.publish_ws_message_received",
            new_callable=AsyncMock,
        ) as mock_publish:
            await mock_link._handle_ws_message(raw_msg)
            args = mock_publish.await_args[1]
            assert args["msg_type"] == "hitl.response"
            assert args["payload"]["command_id"] == 500
            assert args["payload"]["action"] == "confirm"

    @pytest.mark.asyncio
    async def test_hitl_cancel_publishes_hitl_cancel(self, mock_link):
        """hitl.cancel should publish with msg_type='hitl.cancel'."""
        env = create_envelope(
            type=MessageType.HITL_CANCEL,
            body={"command_id": 600, "request_id": "req-1", "thread_id": "th-1"},
        )
        raw_msg = json.dumps(env.model_dump())

        with patch(
            "app.core.engine.event.publishers.publish_ws_message_received",
            new_callable=AsyncMock,
        ) as mock_publish:
            await mock_link._handle_ws_message(raw_msg)
            args = mock_publish.await_args[1]
            assert args["msg_type"] == "hitl.cancel"
            assert args["payload"]["command_id"] == 600

    @pytest.mark.asyncio
    async def test_command_ack_logged_not_published(self, mock_link):
        """command.ack should be logged but not published."""
        env = create_envelope(
            type=MessageType.COMMAND_ACK,
            body={"command_id": 700, "status": "completed"},
        )
        raw_msg = json.dumps(env.model_dump())

        with patch(
            "app.core.engine.event.publishers.publish_ws_message_received",
            new_callable=AsyncMock,
        ) as mock_publish:
            await mock_link._handle_ws_message(raw_msg)
            mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_system_init_calls_init_handler(self, mock_link):
        """system.init should directly call _on_init_protocol."""
        env = create_envelope(
            type=MessageType.SYSTEM_INIT,
            body={"client_id": "c-1", "device_key": "dk-1"},
        )
        raw_msg = json.dumps(env.model_dump())

        mock_link._LINK_LAYER_HANDLERS = {
            "command.relay": AsyncMock(),
            "system.init": AsyncMock(),
            "system.error": AsyncMock(),
        }
        await mock_link._handle_ws_message(raw_msg)
        mock_link._LINK_LAYER_HANDLERS["system.init"].assert_awaited_once_with(
            mock_link, {"client_id": "c-1", "device_key": "dk-1"}
        )

    @pytest.mark.asyncio
    async def test_system_error_calls_error_handler(self, mock_link):
        """system.error should directly call _on_error_protocol."""
        env = create_envelope(
            type=MessageType.SYSTEM_ERROR,
            body={"code": "invalid_token", "message": "token expired"},
        )
        raw_msg = json.dumps(env.model_dump())

        mock_link._LINK_LAYER_HANDLERS = {
            "command.relay": AsyncMock(),
            "system.init": AsyncMock(),
            "system.error": AsyncMock(return_value=True),
        }
        await mock_link._handle_ws_message(raw_msg)
        mock_link._LINK_LAYER_HANDLERS["system.error"].assert_awaited_once_with(
            mock_link, {"code": "invalid_token", "message": "token expired"}
        )
