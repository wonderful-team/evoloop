import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.routes import voice_ws  # noqa: E402
from app.core.routing import executor as routing_executor  # noqa: E402
from app.core.routing.dispatch_handler import DispatchOutcome  # noqa: E402
from app.core.schemas.canonical import MessageType, create_envelope  # noqa: E402


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
    async def _nodup(_message_id, _ttl=300):
        return False

    monkeypatch.setattr(voice_ws, "is_duplicate", _nodup)
    monkeypatch.setattr(voice_ws, "manager", fake_manager)
    monkeypatch.setattr(routing_executor, "manager", fake_manager)
    monkeypatch.setattr(routing_executor, "envelope_fn", create_envelope)
    monkeypatch.setattr(routing_executor, "message_type", MessageType)

    async def _fake_dispatch(raw, *, thread_id, **_):
        text = raw.get("text", "")
        action_map = {
            "打开微信": ("open_app", {"app": "WeChat"}),
            "静音": ("mute", {}),
            "截图": ("screenshot", {}),
        }
        action, args = action_map.get(text, ("noop", {}))
        body = {
            "thread_id": thread_id,
            "status": "routed",
            "target": {"type": "local", "action": action},
            "params": args,
            "candidates": [],
        }
        env = create_envelope(MessageType.VOICE_ROUTE_RESULT, body)
        await routing_executor.manager.push(thread_id, env.model_dump())
        return DispatchOutcome(handled=True, local_response=body)

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
    monkeypatch.setattr(routing_executor, "manager", fake)
    monkeypatch.setattr(routing_executor, "envelope_fn", create_envelope)
    monkeypatch.setattr(routing_executor, "message_type", MessageType)
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


def test_voice_ws_ping_replies_system_init_pong_current_behavior():
    client = TestClient(_app())
    with client.websocket_connect("/voice/ws") as ws:
        assert ws.receive_json()["type"] == "system.init"
        ws.send_json(create_envelope("ping", {"thread_id": "t1"}).model_dump())
        resp = ws.receive_json()
        assert resp["type"] == "system.init"
        assert resp["body"]["pong"] is True
