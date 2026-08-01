"""Tests for routing/executor.py: thread locks, cancel, push functions."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.voice import executor
from app.core.routing import thread_locks


def setup_function():
    executor.manager = None
    executor.envelope_fn = None
    executor.message_type = None
    thread_locks._thread_locks.clear()
    executor._voice_registry.clear()


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


@pytest.mark.asyncio
class TestMarkConsumeVoice:
    async def test_mark_voice(self):
        await executor._mark_voice("t1", "agent")
        assert executor._voice_registry.get("t1") == "agent"

    async def test_consume_voice(self):
        await executor._mark_voice("t1", "agent")
        await executor.consume_voice("t1")
        assert "t1" not in executor._voice_registry

    async def test_consume_voice_nonexistent(self):
        await executor.consume_voice("nonexistent")


@pytest.mark.asyncio
class TestPushResult:
    async def test_noop_when_manager_none(self):
        executor.manager = None
        await executor.push_voice_result("t1", "done", "ok")

    async def test_push_with_manager(self):
        executor.manager = AsyncMock()
        executor.envelope_fn = None
        executor.message_type = None
        await executor.push_voice_result("t1", "done", "测试完成")
        executor.manager.push.assert_awaited_once()
        args = executor.manager.push.call_args[0]
        assert args[0] == "t1"

    async def test_push_with_envelope(self):
        class FakeMsgType:
            VOICE_ROUTE_RESULT = "voice.route_result"

        executor.manager = AsyncMock()
        executor.envelope_fn = MagicMock(return_value={"enveloped": True})
        executor.message_type = FakeMsgType()
        await executor.push_voice_result("t1", "done", "ok")
        executor.envelope_fn.assert_called_once_with(
            "voice.route_result",
            {
                "thread_id": "t1",
                "status": "done",
                "summary": "ok",
            },
        )

    async def test_push_token_noop_when_manager_none(self):
        executor.manager = None
        executor.envelope_fn = None
        executor.message_type = None
        await executor.push_voice_token("t1", "hello", 0)

    async def test_push_boundary_noop_when_manager_none(self):
        executor.manager = None
        executor.envelope_fn = None
        executor.message_type = None
        await executor.push_voice_tts_boundary("t1", "hello", 0)
