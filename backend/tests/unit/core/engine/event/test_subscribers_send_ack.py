"""Tests for EngineCommandSubscriber._send_ack —— P0 final ack path."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.engine.event.subscribers import EngineCommandSubscriber


@pytest.fixture
def subscriber():
    return EngineCommandSubscriber()


class TestSendAck:
    """_send_ack —— 命令最终完成/失败状态上报"""

    @pytest.mark.asyncio
    async def test_send_ack_completed(self, subscriber):
        """completed ack: sends canonical command.ack envelope with command_id + completed status."""
        with patch("app.core.channel.channel_registry") as mock_registry:
            mock_ch = MagicMock()
            mock_ch.send_envelope = AsyncMock()
            mock_registry.get.return_value = mock_ch

            await subscriber._send_ack(cmd_id=42, status="completed")

            mock_ch.send_envelope.assert_awaited_once()
            kwargs = mock_ch.send_envelope.await_args.kwargs
            assert kwargs["env_type"] == "command.ack"
            assert kwargs["body"]["command_id"] == 42
            assert kwargs["body"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_send_ack_failed_with_error(self, subscriber):
        """failed ack: canonical command.ack envelope includes error field."""
        with patch("app.core.channel.channel_registry") as mock_registry:
            mock_ch = MagicMock()
            mock_ch.send_envelope = AsyncMock()
            mock_registry.get.return_value = mock_ch

            await subscriber._send_ack(
                cmd_id=7, status="failed", error="Something broke"
            )

            mock_ch.send_envelope.assert_awaited_once()
            kwargs = mock_ch.send_envelope.await_args.kwargs
            assert kwargs["env_type"] == "command.ack"
            assert kwargs["body"]["command_id"] == 7
            assert kwargs["body"]["status"] == "failed"
            assert kwargs["body"]["error"] == "Something broke"

    @pytest.mark.asyncio
    async def test_send_ack_link_none(self, subscriber):
        """channel 为 None 时静默跳过"""
        with patch("app.core.channel.channel_registry") as mock_registry:
            mock_registry.get.return_value = None

            await subscriber._send_ack(cmd_id=1, status="completed")

    @pytest.mark.asyncio
    async def test_send_ack_logs_success(self, subscriber):
        """成功发送后记录 INFO 日志"""
        with (
            patch("app.core.channel.channel_registry") as mock_registry,
            patch("app.core.engine.event.subscribers.logger") as mock_logger,
        ):
            mock_ch = MagicMock()
            mock_ch.send_envelope = AsyncMock()
            mock_registry.get.return_value = mock_ch

            await subscriber._send_ack(cmd_id=42, status="completed")

            mock_logger.info.assert_called_once_with(
                "[EngineCommand] command.ack sent: cmd_id=42, status=completed"
            )
