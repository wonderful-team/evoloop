"""L0 macro execution dispatch integration test.

Tests the channel-agnostic action layer and the voice router's presentation
layer without requiring a real backend, database, or classifier.  The L0
decision logic itself is mocked out where it would otherwise depend on external
state; the focus is on making sure builtin/macro outcomes are correctly
marshalled into voice.route_result pushes.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel.input.voice_input import VoiceInputChannel
from app.core.routing import executor as routing_executor
from app.core.routing.actions import run_builtin, run_macro
from app.core.routing.channels.voice import execute_route_for_voice
from app.core.routing.executor import push_macro_result
from app.core.routing.local_matcher import LocalMatcher
from app.core.routing.schemas import RouteDecision
from tests.unit.core.routing import fixtures as routing_fixtures


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
        self.workers[thread_id] = {"task": task, "description": description}

    async def get_worker(self, thread_id):
        return None

    async def cancel_worker(self, thread_id):
        entry = self.workers.pop(thread_id, None)
        if entry and not entry["task"].done():
            entry["task"].cancel()
            try:
                await entry["task"]
            except asyncio.CancelledError:
                pass
            return True
        return False


@pytest.fixture(autouse=True)
def _voice_routing_globals():
    """Bind a fake manager/envelope so pushes can be inspected."""
    old_manager = routing_executor.manager
    old_envelope = routing_executor.envelope_fn
    old_message_type = routing_executor.message_type

    manager = FakeManager()
    routing_executor.manager = manager
    routing_executor.envelope_fn = lambda mt, body: {"type": mt, "body": body}
    routing_executor.message_type = MagicMock(VOICE_ROUTE_RESULT="voice.route_result")

    yield manager

    routing_executor.manager = old_manager
    routing_executor.envelope_fn = old_envelope
    routing_executor.message_type = old_message_type
    routing_executor._voice_registry.clear()


@pytest.fixture
def chan():
    """Return a VoiceInputChannel with fakes, but use the patched routing globals."""
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


class TestBuiltinActions:
    """Verify builtin actions produce the right voice.route_result pushes."""

    @pytest.mark.asyncio
    async def test_end_push(self, _voice_routing_globals):
        outcome = await run_builtin(
            "end", {}, thread_id="thread-1", worker_registry=FakeWorkerRegistry()
        )
        await push_macro_result(
            "thread-1", "done" if outcome.ok else "failed", outcome.message
        )
        assert _voice_routing_globals.pushes
        tid, env = _voice_routing_globals.pushes[-1]
        assert env["body"]["status"] == "done"
        assert env["body"]["summary"] == "再见"

    @pytest.mark.asyncio
    async def test_ack_push(self, _voice_routing_globals):
        outcome = await run_builtin(
            "ack", {}, thread_id="thread-1", worker_registry=FakeWorkerRegistry()
        )
        await push_macro_result(
            "thread-1", "done" if outcome.ok else "failed", outcome.message
        )
        assert _voice_routing_globals.pushes
        tid, env = _voice_routing_globals.pushes[-1]
        assert env["body"]["status"] == "done"
        assert env["body"]["summary"] == "好的"

    @pytest.mark.asyncio
    async def test_cancel_noop_push(self, _voice_routing_globals):
        """Cancel with no running worker should push a 'done' result."""
        outcome = await run_builtin(
            "cancel", {}, thread_id="thread-1", worker_registry=FakeWorkerRegistry()
        )
        status = "cancelled" if outcome.data.get("cancelled") else "done"
        await push_macro_result("thread-1", status, outcome.message)
        assert _voice_routing_globals.pushes
        tid, env = _voice_routing_globals.pushes[-1]
        assert env["body"]["status"] == "done"
        assert "没有" in env["body"]["summary"]

    @pytest.mark.asyncio
    async def test_cancel_with_worker_push(self, _voice_routing_globals):
        """Cancel should cancel the running worker and push 'cancelled'."""
        registry = FakeWorkerRegistry()
        task = asyncio.create_task(asyncio.sleep(10))
        await registry.register_worker("thread-1", task)

        outcome = await run_builtin(
            "cancel", {}, thread_id="thread-1", worker_registry=registry
        )
        status = "cancelled" if outcome.data.get("cancelled") else "done"
        await push_macro_result("thread-1", status, outcome.message)
        assert _voice_routing_globals.pushes
        tid, env = _voice_routing_globals.pushes[-1]
        assert env["body"]["status"] == "cancelled"
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_rename_push(self, _voice_routing_globals):
        outcome = await run_builtin(
            "rename",
            {"name": "小爱"},
            thread_id="thread-1",
            worker_registry=FakeWorkerRegistry(),
        )
        await push_macro_result(
            "thread-1", "done" if outcome.ok else "failed", outcome.message
        )
        assert _voice_routing_globals.pushes
        tid, env = _voice_routing_globals.pushes[-1]
        assert env["body"]["status"] == "done"
        assert "小爱" in env["body"]["summary"]


class TestMacroActions:
    """Verify macro execution results are pushed correctly."""

    @pytest.mark.asyncio
    async def test_macro_not_found(self, _voice_routing_globals):
        with patch("app.core.routing.actions.load_macro", AsyncMock(return_value=None)):
            outcome = await run_macro(999, {}, thread_id="thread-1", project_id=1)
            await push_macro_result(
                "thread-1", "done" if outcome.ok else "failed", outcome.message
            )
            tid, env = _voice_routing_globals.pushes[-1]
            assert env["body"]["status"] == "failed"
            assert "未找到" in env["body"]["summary"]

    @pytest.mark.asyncio
    async def test_macro_not_routable(self, _voice_routing_globals):
        macro = MagicMock()
        macro.is_routable.return_value = False
        macro.status = "draft"
        with patch(
            "app.core.routing.actions.load_macro", AsyncMock(return_value=macro)
        ):
            outcome = await run_macro(1, {}, thread_id="thread-1", project_id=1)
            await push_macro_result(
                "thread-1", "done" if outcome.ok else "failed", outcome.message
            )
            tid, env = _voice_routing_globals.pushes[-1]
            assert env["body"]["status"] == "failed"
            assert (
                "not active" in env["body"]["summary"].lower()
                or "未激活" in env["body"]["summary"]
            )

    @pytest.mark.asyncio
    async def test_macro_success(self, _voice_routing_globals):
        macro = MagicMock()
        macro.id = 42
        macro.is_routable.return_value = True
        macro.parameters = []
        macro.macro_script = "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: beep\n"

        from app.core.execution.macro.runner import ExecutionOutcome

        with patch(
            "app.core.routing.actions.load_macro", AsyncMock(return_value=macro)
        ):
            with patch(
                "app.core.routing.actions.run_deterministic",
                AsyncMock(return_value=ExecutionOutcome(True, "OK")),
            ):
                outcome = await run_macro(42, {}, thread_id="thread-1", project_id=1)
                await push_macro_result(
                    "thread-1", "done" if outcome.ok else "failed", outcome.message
                )
                tid, env = _voice_routing_globals.pushes[-1]
                assert env["body"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_macro_timeout(self, _voice_routing_globals):
        macro = MagicMock()
        macro.id = 42
        macro.is_routable.return_value = True
        macro.parameters = []
        macro.macro_script = "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: beep\n"

        async def _slow(*_args, **_kw):
            await asyncio.sleep(10)
            return None

        with patch(
            "app.core.routing.actions.load_macro", AsyncMock(return_value=macro)
        ):
            with patch("app.core.routing.actions.run_deterministic", _slow):
                outcome = await run_macro(
                    42, {}, thread_id="thread-1", project_id=1, timeout=0.1
                )
                await push_macro_result(
                    "thread-1", "done" if outcome.ok else "failed", outcome.message
                )
                tid, env = _voice_routing_globals.pushes[-1]
                assert env["body"]["status"] == "failed"
                assert "超时" in env["body"]["summary"]


class TestVoiceRouterExecuteRoute:
    """Verify execute_route_for_voice marshals CommandRouter decisions into pushes."""

    @pytest.mark.asyncio
    async def test_execute_route_builtin(self, _voice_routing_globals):
        decision = RouteDecision(
            status="routed",
            target_type="builtin",
            target={"type": "builtin", "action": "end"},
            params={},
            confidence=1.0,
            source="voice",
        )
        with patch(
            "app.core.routing.channels.voice.CommandRouter.resolve",
            AsyncMock(return_value=decision),
        ):
            handled = await execute_route_for_voice(
                "再见", thread_id="thread-1", project_id=1
            )
            assert handled is True
            assert _voice_routing_globals.pushes
            tid, env = _voice_routing_globals.pushes[-1]
            assert env["body"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_execute_route_agent(self, _voice_routing_globals):
        decision = RouteDecision(
            status="delegate",
            target_type="agent",
            target={"type": "agent"},
            params={},
            confidence=0.0,
            source="voice",
        )
        with patch(
            "app.core.routing.channels.voice.CommandRouter.resolve",
            AsyncMock(return_value=decision),
        ):
            handled = await execute_route_for_voice(
                "今天天气怎么样", thread_id="thread-1", project_id=1
            )
            assert handled is False


class TestVoiceInputReceive:
    """Verify VoiceInputChannel.receive only normalizes voice.route payloads."""

    @pytest.mark.asyncio
    async def test_receive_normalizes(self, chan):
        with patch(
            "app.core.channel.input.voice_input.identity_service.get_member_id",
            AsyncMock(return_value=7),
        ):
            result = await chan.receive(
                {"thread_id": "t1", "text": "今天天气怎么样", "project_id": "1"}
            )
            assert result is not None
            assert result.source == "voice"
            assert result.thread_id == "t1"
            assert result.text == "今天天气怎么样"
            assert result.project_id == 1
            assert result.member_id == 7
            assert result.metadata == {"source": "voice", "voice_thread_id": "t1"}

    @pytest.mark.asyncio
    async def test_receive_empty(self, chan):
        result = await chan.receive({"thread_id": "t1", "text": ""})
        assert result is None

    @pytest.mark.asyncio
    async def test_receive_running_worker_metadata(self, chan):
        class RunningWorker:
            status = "running"
            description = "worker-desc"

        chan._worker_registry = MagicMock()
        chan._worker_registry.get_worker = AsyncMock(return_value=RunningWorker())
        with patch(
            "app.core.channel.input.voice_input.identity_service.get_member_id",
            AsyncMock(return_value=1),
        ):
            result = await chan.receive({"thread_id": "t1", "text": "你好"})
            assert result is not None
            assert result.metadata["has_running_worker"] == "true"
            assert result.metadata["running_worker_desc"] == "worker-desc"


class TestMatchingAndTiming:
    """Performance and edge case tests for the deterministic L0 matcher."""

    # Minimal dictionaries that make the built-in templates match with concrete values.
    _SLOT_DICTS = {
        "delta": dict(routing_fixtures._DELTA_DICT),
        "key": dict(routing_fixtures._KEY_DICT),
        "app": [
            {"name": "Apple Music", "aliases": ["音乐"]},
            {"name": "Safari", "aliases": ["浏览器"]},
            {"name": "微信", "aliases": ["WeChat"]},
        ],
    }
    _ALIASES = {"音乐": "Apple Music", "浏览器": "Safari"}

    def test_builtin_concrete_patterns_match(self):
        m = LocalMatcher(
            templates=routing_fixtures._TEMPLATES,
            slot_dictionaries=self._SLOT_DICTS,
            aliases=self._ALIASES,
        )
        cases = [
            ("暂停", "play_pause"),
            ("继续播放", "play_pause"),
            ("下一首", "next_track"),
            ("上一首", "prev_track"),
            ("静音", "mute"),
            ("取消静音", "unmute"),
            ("音量调大一点", "set_volume"),
            ("截图", "screenshot"),
            ("锁屏", "lock_screen"),
            ("按一下空格", "press_key"),
            ("打开微信", "open_app"),
            ("切换到音乐", "focus_app"),
            ("退出浏览器", "quit_app"),
            ("再见", "end"),
            ("对的", "ack"),
            ("取消", "cancel"),
            ("你以后叫小爱", "rename"),
        ]
        errors = []
        for text, expected in cases:
            result = m.match(text)
            if result is None:
                errors.append(f"{text!r} → 未匹配 (期望 {expected})")
            elif result[0] != expected:
                errors.append(f"{text!r} → {result[0]} (期望 {expected})")
        assert not errors, "\n".join(errors[:10])

    def test_no_false_positives(self):
        m = LocalMatcher(
            templates=routing_fixtures._TEMPLATES,
            slot_dictionaries=self._SLOT_DICTS,
            aliases=self._ALIASES,
        )
        distractors = [
            "今天天气怎么样",
            "我上个月买的耳机在哪里",
            "下一首歌叫什么",
            "把音量大一点再静音",
        ]
        for d in distractors:
            assert m.match(d) is None, f"{d!r} 不应匹配"

    def test_matching_speed(self):
        m = LocalMatcher(
            templates=routing_fixtures._TEMPLATES,
            slot_dictionaries=self._SLOT_DICTS,
            aliases=self._ALIASES,
        )
        queries = ["暂停", "打开微信", "音量调大一点", "今天天气怎么样"]
        # Warm-up
        for _ in range(100):
            m.match("再见")
        t0 = time.perf_counter()
        iterations = 5000
        for _ in range(iterations):
            for q in queries:
                m.match(q)
        elapsed = time.perf_counter() - t0
        total = iterations * len(queries)
        avg_us = elapsed / total * 1e6
        assert avg_us < 100, f"平均匹配耗时 {avg_us:.1f} µs，超出 100 µs 预算"
