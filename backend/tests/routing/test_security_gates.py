"""VLA voice security gates (design §14.7 security row).

- Gate 1: voice WebSocket rejects non-loopback peers with close code 4403.
- Gate 2: `/route/*` HTTP endpoints reject non-loopback peers with 403, allow loopback.
- Gate 3: the backend NEVER executes a `local` decision (even a destructive one
  like quit_app) — local execution is the client's job (§8.2), so a forged/misrouted
  local decision must be a server-side no-op (no dispatch, no pushback).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import route as route_api
from app.core.routing import deps, executor
from app.core.routing.schemas import RouteDecision

# ---- Gate 1: WS loopback (close 4403) --------------------------------------

def _fake_ws(host: str | None, close_mock: AsyncMock) -> SimpleNamespace:
    client = SimpleNamespace(host=host) if host is not None else None
    return SimpleNamespace(client=client, close=close_mock)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ws_rejects_non_loopback_with_4403() -> None:
    close = AsyncMock()
    ws = _fake_ws("8.8.8.8", close)

    ok = await deps.enforce_loopback_ws(ws)

    assert ok is False
    close.assert_awaited_once()
    assert close.call_args.kwargs.get("code") == 4403


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
async def test_ws_allows_loopback(host: str) -> None:
    close = AsyncMock()
    ws = _fake_ws(host, close)

    ok = await deps.enforce_loopback_ws(ws)

    assert ok is True
    close.assert_not_awaited()


# ---- Gate 2: /route/* HTTP loopback (403 vs allow) --------------------------

def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(route_api.router, prefix="/route")
    return app


@pytest.mark.unit
def test_route_init_rejects_non_loopback_with_403(monkeypatch) -> None:
    # TestClient host is "testclient" (whitelisted); force the predicate to False
    # to simulate a real non-loopback peer arriving at the dependency.
    monkeypatch.setattr(deps, "is_loopback_host", lambda _h: False)
    client = TestClient(_app())

    resp = client.get("/route/init")

    assert resp.status_code == 403
    assert resp.json().get("detail") == "loopback only"


@pytest.mark.unit
def test_route_init_allows_loopback(monkeypatch) -> None:
    monkeypatch.setattr(deps, "is_loopback_host", lambda _h: True)
    client = TestClient(_app())

    resp = client.get("/route/init")

    # no cached spec -> 202 pending; cached -> 200. Either means the gate passed.
    assert resp.status_code in (200, 202)


# ---- Gate 3: backend never executes a local (incl. destructive) decision -----

@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["quit_app", "lock_screen", "press_key"])
async def test_backend_local_decision_is_noop(action: str, monkeypatch) -> None:
    async def _boom(*_a, **_k):  # must never be reached for local
        raise AssertionError(f"backend must not execute local action {action}")

    monkeypatch.setattr(executor, "_run_skill", _boom)
    monkeypatch.setattr(executor, "_run_agent", _boom)
    push = AsyncMock()
    monkeypatch.setattr(executor.manager, "push", push)

    decision = RouteDecision(
        status="routed", target_type="local",
        target={"type": "local", "id": action}, params={"app": "微信"},
    )

    await executor.execute("t-sec", decision)  # must not raise, must not dispatch

    push.assert_not_awaited()  # no failed pushback for local
