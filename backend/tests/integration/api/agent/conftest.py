"""Conftest for agent route integration tests.

Agent chat routes depend on ``validate_guest_access`` (via ``Depends``), so the
auth dependency overrides are applied on the same app.  The shared parent
``client`` fixture is shadowed here with a corrected ``verify_guest_access``
override whose signature declares no fake query params (which FastAPI would
otherwise parse from ``*args, **kwargs``), causing 422s on these routes.
"""

from __future__ import annotations

import httpx
import pytest


class AsyncCtxManager:
    """Minimal async context manager for mocking ``async with ...``."""

    async def __aenter__(self):
        return None

    async def __aexit__(self, *_args):
        return False


class AsyncMethod:
    """Reusable async method returning a configured value."""

    def __init__(self, return_value=None):
        self._return_value = return_value

    async def __call__(self, *args, **kwargs):
        return self._return_value


class SyncMethod:
    """Reusable sync method returning a configured value.

    For mocking interfaces that are sync in production —
    e.g. ``AgentSession.inject_user_message`` / ``inject_resume``, which push a
    ``GateEvent`` synchronously and are consumed by the async session loop.
    Using an ``AsyncMethod`` here produces un-awaited coroutines and runtime
    warnings, since the route layer correctly calls them without ``await``.
    """

    def __init__(self, return_value=None):
        self._return_value = return_value

    def __call__(self, *args, **kwargs):
        return self._return_value


class FakeSharedState:
    """Fake for ``app.core.state.shared_state``."""

    def __init__(self, active_project_id: int = 0):
        self.active = active_project_id

    async def get_active_project_id(self) -> int:
        return self.active

    async def set_active_project_id(self, project_id: int) -> None:
        self.active = project_id


class FakeActivityMonitor:
    """Fake for ``activity_monitor`` just enough for agent routes."""

    def __init__(self):
        self.end_run = AsyncMethod(None)
        self.clear_human_request = AsyncMethod(None)


class FakeSessionManager:
    """Fake for ``session_manager`` (patched on its source module)."""

    def __init__(self):
        self.submit = AsyncMethod(None)
        self.stop_agent = AsyncMethod(None)
        self.stop_all = AsyncMethod(None)
        self.return_get = None

    def get(self, thread_id):
        return self.return_get


@pytest.fixture
def patched_shared_state(monkeypatch):
    """Patch ``app.core.state.shared_state`` to a controllable fake."""
    fake = FakeSharedState()
    monkeypatch.setattr("app.core.state.shared_state", fake)
    return fake


@pytest.fixture
def patched_session_manager(monkeypatch):
    """Patch ``session_manager`` on its source module."""
    fake = FakeSessionManager()
    monkeypatch.setattr("app.core.engine.session.manager.session_manager", fake)
    return fake


@pytest.fixture
async def client():
    """``httpx.AsyncClient`` over a minimal FastAPI app with clean auth deps."""
    from fastapi import FastAPI

    import app.api.deps as deps
    from app.api.main import api_router
    from app.models import User

    test_app = FastAPI(title="evo-api-test-agent")
    test_app.include_router(api_router)

    test_app.dependency_overrides[deps.oauth2_scheme] = lambda: "test-token"
    test_app.dependency_overrides[deps.oauth2_scheme_optional] = lambda: "test-token"

    async def _fake_user():
        return User(id=1, is_active=True, name="tester")

    test_app.dependency_overrides[deps.get_current_user] = _fake_user
    test_app.dependency_overrides[deps.get_current_user_optional] = _fake_user

    async def _ok_guest():
        return None

    test_app.dependency_overrides[deps.verify_guest_access] = _ok_guest

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30.0
    ) as c:
        yield c

    test_app.dependency_overrides.clear()
