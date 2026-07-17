import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.routes import voice_ws  # noqa: E402
from app.core.routing import executor, retriever  # noqa: E402
from app.core.routing import router as route_router  # noqa: E402
from app.core.routing.schemas import RouteDecision  # noqa: E402
from app.core.schemas.canonical import create_envelope  # noqa: E402


class _FakeManager:
    def __init__(self):
        self.bound = []
        self.pushes = []

    async def bind_thread(self, tid, cid):
        self.bound.append((tid, cid))

    async def push(self, tid, env):
        self.pushes.append((tid, env))
        return True


def _patch_route(monkeypatch, decision):
    async def _retrieve(_text, **_kwargs):
        return []

    async def _route(_req, _candidates):
        return decision

    async def _nodup(_message_id, _ttl=300):
        return False

    monkeypatch.setattr(retriever, "retrieve", _retrieve)
    monkeypatch.setattr(route_router, "route", _route)
    monkeypatch.setattr(voice_ws, "is_duplicate", _nodup)


@pytest.mark.asyncio
async def test_handle_route_local(monkeypatch):
    fake = _FakeManager()
    monkeypatch.setattr(voice_ws, "manager", fake)
    _patch_route(
        monkeypatch,
        RouteDecision(
            status="routed",
            target_type="local",
            target={"type": "local", "id": "open_app"},
            params={"app": "微信"},
        ),
    )

    await voice_ws._handle_route(
        {"text": "打开微信", "thread_id": "t1", "message_id": "m1"}, "c1"
    )

    assert ("t1", "c1") in fake.bound
    assert len(fake.pushes) == 1
    tid, env = fake.pushes[0]
    assert tid == "t1"
    assert env["type"] == "voice.route_result"
    assert env["body"]["target"]["type"] == "local"
    assert env["body"]["target"]["id"] == "open_app"


@pytest.mark.asyncio
async def test_handle_route_skill_pushes_routed(monkeypatch):
    fake = _FakeManager()
    monkeypatch.setattr(voice_ws, "manager", fake)
    _patch_route(
        monkeypatch,
        RouteDecision(
            status="routed",
            target_type="skill",
            target={"type": "skill", "id": 42},
            params={"song": "晴天"},
        ),
    )

    await voice_ws._handle_route(
        {"text": "播放晴天", "thread_id": "t2", "message_id": "m2"}, "c2"
    )

    assert len(fake.pushes) == 1
    _, env = fake.pushes[0]
    assert env["body"]["target"]["type"] == "skill"
    assert env["body"]["target"]["id"] == 42


@pytest.mark.asyncio
async def test_executor_pushes_done(monkeypatch):
    # Contract-level: a skill decision makes executor.execute push a terminal
    # `done`. Branch-level executor logic is covered by test_executor.py.
    fake = _FakeManager()
    monkeypatch.setattr(executor, "manager", fake)

    async def _fake_execute(tid, _decision):
        from app.core.schemas.canonical import MessageType, create_envelope

        await executor.manager.push(
            tid,
            create_envelope(
                MessageType.VOICE_ROUTE_RESULT,
                {"thread_id": tid, "status": "done", "summary": "已为你执行技能"},
            ).model_dump(),
        )

    monkeypatch.setattr(executor, "execute", _fake_execute)
    decision = RouteDecision(
        status="routed", target_type="skill", target={"type": "skill", "id": 7}
    )

    await executor.execute("t3", decision)

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
