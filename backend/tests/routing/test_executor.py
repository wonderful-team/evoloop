"""Tests for routing/executor.py: thread locks, cancel, and push delegations."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.routing import thread_locks
from app.core.voice import executor


def setup_function():
    thread_locks._thread_locks.clear()


class TestThreadLock:
    @pytest.mark.asyncio
    async def test_get_thread_lock_creates_new(self):
        lock = await thread_locks.get_thread_lock("t1")
        assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_get_thread_lock_reuses_existing(self):
        lock1 = await thread_locks.get_thread_lock("t1")
        lock2 = await thread_locks.get_thread_lock("t1")
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_get_thread_lock_per_thread(self):
        lock1 = await thread_locks.get_thread_lock("t1")
        lock2 = await thread_locks.get_thread_lock("t2")
        assert lock1 is not lock2


@pytest.mark.asyncio
class TestCancelVoiceTask:
    @patch("app.core.voice.executor.worker_registry")
    async def test_cancel_calls_worker_registry(self, mock_registry):
        mock_registry.cancel_worker = AsyncMock(return_value=True)
        result = await executor.cancel_voice_task("t1")
        assert result is True
        mock_registry.cancel_worker.assert_awaited_once_with("t1")


# TestMarkConsumeVoice removed: _voice_registry and _mark_voice/consume_voice
# were deleted as part of the OutputChannelPolicy refactor.
# Voice session tracking now uses EvoContext.metadata.source + current_session_source ContextVar.


@pytest.mark.asyncio
class TestPushDelegatesToVoiceChannel:
    """Legacy executor push helpers are now thin wrappers around VoiceChannel."""

    async def test_push_voice_result_delegates(self):
        with patch(
            "app.core.channel.output.voice_channel.VoiceChannel.push_voice_result"
        ) as mock_push:
            await executor.push_voice_result("t1", "done", "ok", skip_tts=True)
            mock_push.assert_awaited_once_with("t1", "done", "ok", skip_tts=True)

    async def test_push_voice_token_delegates(self):
        with patch(
            "app.core.channel.output.voice_channel.VoiceChannel.push_voice_token"
        ) as mock_push:
            await executor.push_voice_token("t1", "hello", 0)
            mock_push.assert_awaited_once_with("t1", "hello", 0)

    async def test_push_voice_tts_boundary_delegates(self):
        with patch(
            "app.core.channel.output.voice_channel.VoiceChannel.push_voice_tts_boundary"
        ) as mock_push:
            await executor.push_voice_tts_boundary("t1", "hello", 0)
            mock_push.assert_awaited_once_with("t1", "hello", 0)

    async def test_push_tts_text_delegates(self):
        with patch(
            "app.core.channel.output.voice_channel.VoiceChannel.push_tts_text"
        ) as mock_push:
            await executor.push_tts_text("t1", "确认")
            mock_push.assert_awaited_once_with("t1", "确认")

    async def test_push_macro_result_delegates(self):
        with patch(
            "app.core.channel.output.voice_channel.VoiceChannel.push_macro_result"
        ) as mock_push:
            await executor.push_macro_result("t1", "done", "ok")
            mock_push.assert_awaited_once_with("t1", "done", "ok")

    async def test_handle_navigate_delegates(self):
        with patch(
            "app.core.channel.output.voice_channel.VoiceChannel.handle_navigate"
        ) as mock_push:
            await executor.handle_navigate("/home", "t1", feedback="完成")
            mock_push.assert_awaited_once_with("/home", "t1", feedback="完成")

    async def test_push_local_result_delegates(self):
        with patch(
            "app.core.channel.output.voice_channel.VoiceChannel.push_local_result"
        ) as mock_push:
            await executor.push_local_result("t1", "screenshot", {})
            mock_push.assert_awaited_once_with("t1", "screenshot", {})
