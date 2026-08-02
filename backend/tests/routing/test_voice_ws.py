import asyncio
import time
from typing import Any

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.routes import voice_ws  # noqa: E402
from app.core.channel.base import ChannelContext  # noqa: E402
from app.core.channel.output.voice_channel import VoiceChannel  # noqa: E402
from app.core.routing.actions import ActionOutcome  # noqa: E402
from app.core.routing.dispatch_handler import DispatchOutcome  # noqa: E402
from app.core.schemas.canonical import MessageType, create_envelope  # noqa: E402
from app.core.voice import executor as routing_executor  # noqa: E402
from app.models.schemas.events import TokenEvent  # noqa: E402


def _envelope_dict(mtype, body):
    """Return a serialized dict as required by VoiceChannel.bind()."""
    return create_envelope(mtype, body).model_dump()


@pytest.fixture(autouse=True)
def _reset_voice_input_binding(monkeypatch):
    """Force _ensure_voice_input to rebind on the next _handle_route call.

    Without this, an earlier integration test that monkeypatches
    worker_registry can leave voice_input bound to a fake registry and break
    worker-survival assertions here.
    """
    monkeypatch.setattr(voice_ws, "_voice_input_bound", False)
    yield


class _FakeManager:
    def __init__(self):
        self.bound = []
        self.pushes = []

    async def bind_thread(self, tid, cid):
        self.bound.append((tid, cid))

    async def push(self, tid, env):
        self.pushes.append((tid, env))
        return True


def _patch_route(monkeypatch, fake_manager):
    from app.core.channel.output.voice_channel import VoiceChannel

    async def _nodup(_message_id, _ttl=300):
        return False

    monkeypatch.setattr(voice_ws, "is_duplicate", _nodup)
    monkeypatch.setattr(voice_ws, "manager", fake_manager)
    VoiceChannel.bind(
        manager=fake_manager,
        envelope_fn=_envelope_dict,
        message_type=MessageType,
    )

    async def _fake_dispatch(raw, *, thread_id, **_):  # noqa: ARG001
        text = raw.get("text", "")
        action_map = {
            "打开微信": ActionOutcome(ok=True, message="", action_type="local", data={"action": "open_app", "args": {"app": "WeChat"}}),
            "静音": ActionOutcome(ok=True, message="", action_type="local", data={"action": "mute", "args": {}}),
            "截图": ActionOutcome(ok=True, message="已截图", action_type="local", data={"action": "screenshot", "args": {}}),
        }
        ao = action_map.get(text)
        if ao is None:
            return DispatchOutcome(handled=False)
        return DispatchOutcome(handled=True, local_response=ao)

    monkeypatch.setattr(voice_ws, "dispatch_user_message", _fake_dispatch)


@pytest.mark.asyncio
async def test_handle_route_local(monkeypatch):
    fake = _FakeManager()
    _patch_route(monkeypatch, fake)

    await voice_ws._handle_route(
        {"text": "打开微信", "thread_id": "t1", "message_id": "m1"}, "c1"
    )

    assert ("t1", "c1") in fake.bound
    assert len(fake.pushes) == 1
    tid, env = fake.pushes[0]
    assert tid == "t1"
    assert env["type"] == "voice.route_result"
    assert env["body"]["target"]["type"] == "local"
    assert env["body"]["target"]["action"] == "open_app"
    assert env["body"]["params"]["app"] in ("微信", "WeChat")


@pytest.mark.asyncio
async def test_handle_route_l0_mute(monkeypatch):
    fake = _FakeManager()
    _patch_route(monkeypatch, fake)

    await voice_ws._handle_route(
        {"text": "静音", "thread_id": "t3", "message_id": "m3"}, "c3"
    )

    assert len(fake.pushes) == 1
    _, env = fake.pushes[0]
    assert env["body"]["target"]["type"] == "local"
    assert env["body"]["target"]["action"] == "mute"


@pytest.mark.asyncio
async def test_handle_route_l0_screenshot(monkeypatch):
    fake = _FakeManager()
    _patch_route(monkeypatch, fake)

    await voice_ws._handle_route(
        {"text": "截图", "thread_id": "t4", "message_id": "m4"}, "c4"
    )

    assert len(fake.pushes) == 1
    _, env = fake.pushes[0]
    assert env["body"]["status"] == "routed"
    assert env["body"]["target"]["action"] == "screenshot"


@pytest.mark.asyncio
async def test_executor_pushes_done(monkeypatch):
    fake = _FakeManager()
    from app.core.channel.output.voice_channel import VoiceChannel

    monkeypatch.setattr(VoiceChannel, "_manager", fake)
    monkeypatch.setattr(VoiceChannel, "_envelope_fn", _envelope_dict)
    monkeypatch.setattr(VoiceChannel, "_message_type", MessageType)
    monkeypatch.setattr(routing_executor, "active_volc_clients", {})

    await routing_executor.push_voice_result("t3", "done", "已为你执行技能")

    assert len(fake.pushes) == 1
    tid, env = fake.pushes[0]
    assert tid == "t3"
    assert env["type"] == "voice.route_result"
    assert env["body"]["status"] == "done"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(voice_ws.router)
    return app


def test_voice_ws_handshake_and_bad_envelope():
    client = TestClient(_app())
    with client.websocket_connect("/voice/ws") as ws:
        init = ws.receive_json()
        assert init["type"] == "system.init"
        ws.send_json({"foo": "bar"})
        resp = ws.receive_json()
        assert resp["type"] == "system.error"
        assert resp["body"]["code"] == "bad_envelope"


def test_voice_ws_unknown_type_returns_system_error_current_behavior():
    client = TestClient(_app())
    with client.websocket_connect("/voice/ws") as ws:
        assert ws.receive_json()["type"] == "system.init"
        ws.send_json(create_envelope("voice.unknown", {}).model_dump())
        resp = ws.receive_json()
        assert resp["type"] == "system.error"
        assert resp["body"]["code"] == "unknown_type"


def test_voice_ws_start_volc_not_configured_returns_error_and_idle_state(monkeypatch):
    """If Volcengine is not configured, voice.start must not pretend to be listening."""
    monkeypatch.setattr(
        voice_ws.SystemConfigService, "get_value", lambda _key, default=None: None
    )

    client = TestClient(_app())
    with client.websocket_connect("/voice/ws") as ws:
        assert ws.receive_json()["type"] == "system.init"
        ws.send_json(
            create_envelope("voice.start", {"thread_id": "t-no-volc"}).model_dump()
        )
        resp = ws.receive_json()
        assert resp["type"] == "system.error"
        assert resp["body"]["code"] == "volc_not_configured"

        state = ws.receive_json()
        assert state["type"] == "voice:state"
        assert state["body"]["state"] == "idle"
        assert state["body"]["thread_id"] == "t-no-volc"


def test_voice_ws_start_volc_connect_failure_returns_error_and_idle_state(monkeypatch):
    """If Volcengine connect fails, voice.start must surface the error and reset state."""
    monkeypatch.setattr(
        voice_ws.SystemConfigService, "get_value", lambda _key, default=None: "dummy"
    )

    class _FailingVolcClient:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):
            raise ConnectionError("volcengine down")

    monkeypatch.setattr(voice_ws, "VolcDialogClient", _FailingVolcClient)

    client = TestClient(_app())
    with client.websocket_connect("/voice/ws") as ws:
        assert ws.receive_json()["type"] == "system.init"
        ws.send_json(
            create_envelope("voice.start", {"thread_id": "t-volc-fail"}).model_dump()
        )
        resp = ws.receive_json()
        assert resp["type"] == "system.error"
        assert resp["body"]["code"] == "volc_connect_failed"

        state = ws.receive_json()
        assert state["type"] == "voice:state"
        assert state["body"]["state"] == "idle"
        assert state["body"]["thread_id"] == "t-volc-fail"


def test_voice_ws_ping_replies_system_init_pong_current_behavior():
    client = TestClient(_app())
    with client.websocket_connect("/voice/ws") as ws:
        assert ws.receive_json()["type"] == "system.init"
        ws.send_json(create_envelope("ping", {"thread_id": "t1"}).model_dump())
        resp = ws.receive_json()
        assert resp["type"] == "system.init"
        assert resp["body"]["pong"] is True


@pytest.mark.asyncio
async def test_voice_channel_cancel_thread_clears_state_and_blocks_chunks(monkeypatch):
    """Barge-in should stop VoiceChannel from sending more TTS chunks."""
    tid = "t-barge-cancel"
    VoiceChannel.reset_thread(tid)

    sent: list[dict] = []

    class _FakeVolcClient:
        async def send_chat_tts_text(self, *, start: bool, end: bool, content: str) -> None:
            sent.append({"start": start, "end": end, "content": content})

    monkeypatch.setattr(routing_executor, "active_volc_clients", {tid: _FakeVolcClient()})

    vc = VoiceChannel()
    await vc.send(TokenEvent(content="hello "), ChannelContext(thread_id=tid))
    await vc.send(TokenEvent(content="world"), ChannelContext(thread_id=tid))
    assert "hello" in VoiceChannel._tts_accumulator.get(tid, "")

    # Start an actual streaming segment so _tts_started becomes True.
    await vc.push_tts_chunk(tid, "hello world.", end=False)
    assert VoiceChannel._tts_started.get(tid) is True
    assert len(sent) == 1

    was_streaming = VoiceChannel.cancel_thread(tid)
    assert was_streaming is True
    assert tid not in VoiceChannel._tts_started
    assert tid not in VoiceChannel._tts_accumulator
    assert tid in VoiceChannel._cancelled_threads

    await vc.push_tts_chunk(tid, "ignored", end=False)
    assert len(sent) == 1  # only the pre-cancel chunk went through

    VoiceChannel.reset_thread(tid)


@pytest.mark.asyncio
async def test_handle_barge_in_cancels_worker_and_tts_stream(monkeypatch):
    """_handle_barge_in must abort VoiceChannel streaming TTS and NOT cancel the background worker."""
    from app.core.channel.output.voice_channel import VoiceChannel

    tid = "t-barge"
    fake = _FakeManager()
    monkeypatch.setattr(voice_ws, "manager", fake)
    VoiceChannel.bind(
        manager=fake,
        envelope_fn=_envelope_dict,
        message_type=MessageType,
    )

    cancelled = []

    async def _fake_cancel_voice_task(thread_id: str) -> bool:
        cancelled.append(thread_id)
        return True

    monkeypatch.setattr(routing_executor, "cancel_voice_task", _fake_cancel_voice_task)

    VoiceChannel.reset_thread(tid)
    voice_ws._is_sending_chat_tts_text[tid] = False

    await voice_ws._handle_barge_in(tid)

    assert tid not in cancelled  # Verify worker was NOT cancelled (mute-only)
    assert voice_ws._is_sending_chat_tts_text.get(tid) is True
    assert tid in VoiceChannel._cancelled_threads
    assert tid not in VoiceChannel._tts_started

    assert len(fake.pushes) == 1
    _, env = fake.pushes[0]
    assert env["type"] == "voice.barge_in"
    assert env["body"]["thread_id"] == tid

    VoiceChannel.reset_thread(tid)
    voice_ws._is_sending_chat_tts_text.pop(tid, None)


@pytest.mark.asyncio
async def test_barge_in_and_query_worker_survives(monkeypatch):  # noqa: ARG001
    """If user queries progress after barge-in, the worker task remains active."""
    from app.core.channel.input.voice_input import voice_input
    from app.core.engine.worker_registry import worker_registry

    tid = "t-query-survive"

    async def mock_worker():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

    old_task = asyncio.create_task(mock_worker())
    await worker_registry.register_worker(tid, old_task, "old worker")

    # 1. Barge-in (mute-only)
    await voice_ws._handle_barge_in(tid)
    assert not old_task.done()

    # 2. Simulate dispatching query
    async def mock_query():
        pass
    new_task = asyncio.create_task(mock_query())

    # Register the new query task, which puts old_task into previous_tasks
    await worker_registry.register_worker(tid, new_task, "new query task")
    assert tid in worker_registry._previous_tasks

    # 3. Simulate await_and_finalize completing
    # In QUERY path, loop.py did NOT pop or cancel the old task.
    # Therefore, await_and_finalize should restore old task registration.
    await voice_input.await_and_finalize(tid, new_task, old_task, "old worker")

    record = await worker_registry.get_worker(tid)
    assert record.task == old_task
    assert not old_task.done()

    # Clean up
    old_task.cancel()
    await asyncio.gather(old_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_barge_in_and_new_command_cancels_worker(monkeypatch):  # noqa: ARG001
    """If user issues a new command after barge-in, the old worker task gets cancelled."""
    from unittest.mock import AsyncMock, patch

    from app.core.channel.input.voice_input import voice_input
    from app.core.engine.loop import run_node_loop
    from app.core.engine.routers import RoutingTarget
    from app.core.engine.worker_registry import worker_registry

    tid = "t-command-cancel"

    async def mock_worker():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

    old_task = asyncio.create_task(mock_worker())
    await worker_registry.register_worker(tid, old_task, "old worker")

    # 1. Barge-in (mute-only)
    await voice_ws._handle_barge_in(tid)
    assert not old_task.done()

    # 2. Start new command execution task
    async def mock_new_command():
        pass
    new_task = asyncio.create_task(mock_new_command())
    await worker_registry.register_worker(tid, new_task, "new command task")

    # Mock state and patch transition to WORKER
    class MockState:
        next_node = RoutingTarget.SUPERVISOR
        iteration_count = 0
        messages = []
        structured_plan = None
        current_plan = None
        session_goal = "command"
        worker_outcome = None

    class MockSupervisorNode:
        async def __call__(self, state, config):
            from app.core.engine.nodes.supervisor import StateUpdate
            return StateUpdate(messages=[])

    state = MockState()

    with patch("app.core.engine.nodes.supervisor.SupervisorNode", return_value=MockSupervisorNode()), \
         patch("app.core.engine.routers.route_supervisor", return_value=RoutingTarget.WORKER), \
         patch("app.core.monitoring.activity.activity_monitor.check_cancellation", AsyncMock()):
        await run_node_loop(state, {}, tid, max_loop_steps=1)

    await asyncio.sleep(0.01)
    assert old_task.done()  # Old task must be cancelled by the loop gate!

    # await_and_finalize should not restore since it was popped/cancelled
    await voice_input.await_and_finalize(tid, new_task, old_task, "old worker")
    record = await worker_registry.get_worker(tid)
    assert record.task == new_task


@pytest.mark.asyncio
async def test_early_ack_tts_delivery(monkeypatch):
    """Verify that an L1 Agent route triggers an early-ack TTS push with end=True."""
    from unittest.mock import AsyncMock, MagicMock

    from app.core.channel.input.voice_input import voice_input

    tid = "t-early-ack"
    mock_ws = AsyncMock()

    from app.core.channel.base import IncomingMessage
    from app.core.routing.dispatch_handler import DispatchOutcome

    fake_msg = IncomingMessage(
        thread_id=tid,
        source="voice",
        text="hello",
        metadata={"intent_hint": {"domain": "chitchat"}}
    )
    fake_outcome = DispatchOutcome(handled=False, msg=fake_msg, inputs=MagicMock())

    async def mock_dispatch(*_args, **_kwargs):
        return fake_outcome

    monkeypatch.setattr(voice_ws, "dispatch_user_message", mock_dispatch)

    monkeypatch.setattr(voice_input, "post_dispatch", AsyncMock(return_value={"task": AsyncMock(), "old_worker_task": None}))
    monkeypatch.setattr(voice_input, "await_and_finalize", AsyncMock())

    pushed_chunks = []
    async def mock_push_tts_chunk(thread_id, text, end, *, force_start=False):
        pushed_chunks.append((thread_id, text, end, force_start))

    monkeypatch.setattr(VoiceChannel, "push_tts_chunk", mock_push_tts_chunk)

    reset_called = []
    def mock_reset_tts_started(thread_id):
        reset_called.append(thread_id)

    monkeypatch.setattr(VoiceChannel, "reset_tts_started", mock_reset_tts_started)

    await voice_ws._run_agent_pipeline(mock_ws, tid, "hello")

    assert len(pushed_chunks) == 1
    assert pushed_chunks[0][0] == tid
    assert pushed_chunks[0][2] is True  # end=True
    assert pushed_chunks[0][3] is True  # force_start=True

    from app.core.engine.domain_mapping import ACK_TEMPLATES
    assert pushed_chunks[0][1] in ACK_TEMPLATES

    assert tid in reset_called


def test_voice_ws_reconnect_keeps_new_volc_client(monkeypatch):
    """When Rust reconnects, the old connection's teardown must not destroy the new connection's Volcengine client."""
    monkeypatch.setattr(
        voice_ws.SystemConfigService, "get_value", lambda _key, default=None: "dummy"
    )

    clients_created: list[Any] = []

    class _RecordingVolcClient:
        def __init__(self, *args, **kwargs):
            self._id = len(clients_created)
            clients_created.append(self)

        async def connect(self):
            return

        async def close(self):
            return

        async def receive_response(self):
            await asyncio.sleep(3600)

    monkeypatch.setattr(voice_ws, "VolcDialogClient", _RecordingVolcClient)

    client = TestClient(_app())
    tid = "t-reconnect"

    with client.websocket_connect("/voice/ws") as ws1:
        assert ws1.receive_json()["type"] == "system.init"
        ws1.send_json(
            create_envelope("voice.start", {"thread_id": tid}).model_dump()
        )
        state1 = ws1.receive_json()
        assert state1["type"] == "voice:state"
        assert state1["body"]["state"] == "listening"
        assert routing_executor.active_volc_clients[tid] is clients_created[0]

        with client.websocket_connect("/voice/ws") as ws2:
            assert ws2.receive_json()["type"] == "system.init"
            ws2.send_json(
                create_envelope("voice.start", {"thread_id": tid}).model_dump()
            )
            state2 = ws2.receive_json()
            assert state2["type"] == "voice:state"
            assert state2["body"]["state"] == "listening"
            assert routing_executor.active_volc_clients[tid] is clients_created[1]

            # Close the first connection while the second one still owns the thread.
            ws1.close()
            time.sleep(0.2)  # let the server process the disconnect finally
            assert routing_executor.active_volc_clients[tid] is clients_created[1]

    # After both close, the last connection's cleanup should remove the client.
    assert tid not in routing_executor.active_volc_clients
