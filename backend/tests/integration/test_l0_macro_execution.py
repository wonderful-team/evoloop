"""
L0 Macro execution dispatch integration test.

Tests the full chain: LocalMatcher.match() → action resolution →
_dispatch_macro path verification. Mocks WS manager and DesktopController
to verify the execution path without requiring a real backend.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel.input.voice_input import VoiceInputChannel, voice_input
from app.core.routing.init_spec import _TEMPLATES
from app.core.routing.local_matcher import LocalMatcher


class FakeManager:
    """Captures WS pushes for verification."""
    def __init__(self):
        self.pushes = []

    async def push(self, thread_id, envelope):
        self.pushes.append((thread_id, envelope))
        return True


class FakeWorkerRegistry:
    """Captures worker registrations for verification."""
    def __init__(self):
        self.workers = {}

    async def register_worker(self, thread_id, task, description=""):
        self.workers[thread_id] = task

    async def get_worker(self, thread_id):
        return None

    async def cancel_worker(self, thread_id):
        return False


@pytest.fixture
def chan():
    """Return a fully bound VoiceInputChannel with fakes."""
    c = VoiceInputChannel()
    c.bind(
        manager=FakeManager(),
        executor=AsyncMock(),
        state_machine=AsyncMock(),
        state_enum=MagicMock(),
        worker_registry=FakeWorkerRegistry(),
        envelope_fn=lambda mt, body: {"type": mt, "body": body},
        message_type=MagicMock(VOICE_ROUTE_RESULT="voice.route_result"),
    )
    return c


class TestBuiltinCommands:
    """Verify builtin commands produce voice.route_result responses."""

    @pytest.mark.asyncio
    async def test_end_push(self, chan):
        await chan._handle_builtin("thread-1", "end", {})
        assert len(chan._manager.pushes) > 0
        tid, env = chan._manager.pushes[-1]
        assert env["body"]["status"] == "routed"
        assert env["body"]["target"]["action"] == "end"

    @pytest.mark.asyncio
    async def test_ack_push(self, chan):
        await chan._handle_builtin("thread-1", "ack", {})
        assert len(chan._manager.pushes) > 0
        tid, env = chan._manager.pushes[-1]
        assert env["body"]["target"]["action"] == "ack"

    @pytest.mark.asyncio
    async def test_cancel_noop_push(self, chan):
        """Cancel with no running worker should push 'done'."""
        await chan._handle_builtin("thread-1", "cancel", {})
        assert len(chan._manager.pushes) > 0
        tid, env = chan._manager.pushes[-1]
        assert env["body"]["status"] in ("done", "cancelled")

    @pytest.mark.asyncio
    async def test_cancel_with_worker(self, chan):
        """Cancel should call worker_registry.cancel_worker."""
        wr = MagicMock()
        wr.cancel_worker = AsyncMock(return_value=True)
        chan._worker_registry = wr
        await chan._handle_builtin("thread-1", "cancel", {})
        wr.cancel_worker.assert_awaited_once_with("thread-1")
        assert len(chan._manager.pushes) > 0
        tid, env = chan._manager.pushes[-1]
        assert env["body"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_rename_push(self, chan):
        await chan._handle_builtin("thread-1", "rename", {"name": "小爱"})
        assert len(chan._manager.pushes) > 0


class TestMacroDispatch:
    """Verify macro dispatch pushes done/failed status."""

    @pytest.mark.asyncio
    async def test_dispatch_macro_not_found(self, chan):
        # load_macro is imported inside _dispatch_macro from runner
        macro_mod = "app.core.execution.macro.runner.load_macro"
        with patch(macro_mod, AsyncMock(return_value=None)):
            await chan._dispatch_macro("thread-1", 999, {}, 0)
            tid, env = chan._manager.pushes[-1]
            assert env["body"]["status"] == "failed"
            assert "未找到" in env["body"]["summary"]

    @pytest.mark.asyncio
    async def test_dispatch_macro_not_routable(self, chan):
        macro = MagicMock()
        macro.is_routable.return_value = False
        macro_mod = "app.core.execution.macro.runner.load_macro"
        with patch(macro_mod, AsyncMock(return_value=macro)):
            await chan._dispatch_macro("thread-1", 1, {}, 0)
            tid, env = chan._manager.pushes[-1]
            assert env["body"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_dispatch_macro_success(self, chan):
        macro = MagicMock()
        macro.id = 42
        macro.is_routable.return_value = True
        macro.parameters = []
        macro.macro_script = "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: beep\n"
        macro.updated_at = None

        from app.core.execution.macro.runner import ExecutionOutcome

        macro_mod = "app.core.execution.macro.runner.load_macro"
        det_mod = "app.core.execution.macro.runner.run_deterministic"
        with patch(macro_mod, AsyncMock(return_value=macro)):
            with patch(det_mod, AsyncMock(return_value=ExecutionOutcome(True, "OK"))):
                await chan._dispatch_macro("thread-1", 42, {}, 0)
                tid, env = chan._manager.pushes[-1]
                assert env["body"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_dispatch_macro_timeout(self, chan):
        macro = MagicMock()
        macro.id = 42
        macro.is_routable.return_value = True
        macro.parameters = []
        macro.macro_script = "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: beep\n"
        macro.updated_at = None
        import app.core.channel.input.voice_input as vi
        vi._MACRO_TIMEOUT = 0.1

        async def _slow(*a, **kw):
            await asyncio.sleep(10)
            return None

        macro_mod = "app.core.execution.macro.runner.load_macro"
        det_mod = "app.core.execution.macro.runner.run_deterministic"
        with patch(macro_mod, AsyncMock(return_value=macro)):
            with patch(det_mod, _slow):
                await chan._dispatch_macro("thread-1", 42, {}, 0)
                tid, env = chan._manager.pushes[-1]
                assert env["body"]["status"] == "failed"
                assert "超时" in env["body"].get("summary", "")
        vi._MACRO_TIMEOUT = 5.0


class TestReceiveL0Split:
    """Verify receive() correctly splits macro: vs builtin."""

    @pytest.mark.asyncio
    async def test_receive_macro(self, chan):
        """Builtin '再见' should return None (no agent dispatch)."""
        result = await chan.receive({
            "thread_id": "t1",
            "text": "再见",
            "project_id": "1",
        })
        assert result is None  # L0 handled, no agent dispatch

    @pytest.mark.asyncio
    async def test_receive_agent(self, chan):
        """Non-L0 utterance should return IncomingMessage."""
        result = await chan.receive({
            "thread_id": "t1",
            "text": "今天天气怎么样",
            "project_id": "1",
        })
        assert result is not None
        assert result.source == "voice"

    @pytest.mark.asyncio
    async def test_receive_empty(self, chan):
        result = await chan.receive({"text": "", "thread_id": "t1"})
        assert result is None


class TestMatchingAndTiming:
    """Performance and edge case tests for L0 matching."""

    ALL_PATTERNS = []
    for t in _TEMPLATES:
        ALL_PATTERNS.extend(t.get("patterns", []))

    def test_all_builtin_patterns_match(self):
        m = LocalMatcher(templates=_TEMPLATES)
        errors = []
        for tpl in _TEMPLATES:
            expected = tpl["action"]
            for pattern in tpl.get("patterns", []):
                result = m.match(pattern)
                if result is None:
                    errors.append(f"'{pattern}' → 未匹配 (期望 {expected})")
                elif result[0] != expected:
                    errors.append(f"'{pattern}' → {result[0]} (期望 {expected})")
        assert not errors, "\n".join(errors[:10])

    def test_no_false_positives(self):
        m = LocalMatcher(templates=_TEMPLATES)
        distractors = [
            "今天天气怎么样", "打开微信给张三发消息",
            "我上个月买的耳机在哪里",
        ]
        for d in distractors:
            assert m.match(d) is None, f"'{d}' 不应匹配"

    def test_matching_speed(self):
        m = LocalMatcher(templates=_TEMPLATES)
        import time
        queries = self.ALL_PATTERNS + ["今天天气怎么样"]
        n = len(queries)
        # Warm-up
        for _ in range(100):
            m.match("再见")
        t0 = time.perf_counter()
        iterations = 5000
        for _ in range(iterations):
            for q in queries:
                m.match(q)
        elapsed = time.perf_counter() - t0
        avg = elapsed / (n * iterations) * 1_000_000
        total_ms = elapsed / iterations * 1000
        print(f"\n  [{self.__class__.__name__}] {n} queries × {iterations} "
              f"= {avg:.1f}μs/match, {total_ms:.2f}ms/batch")
        assert total_ms < 50, f"Too slow: {total_ms:.2f}ms"
