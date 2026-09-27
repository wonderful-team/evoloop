"""Conftest for memory route integration tests.

Extends the shared API harness by overriding ``get_memory_manager`` (a
FastAPI ``Depends``) to yield a controllable fake manager instead of hitting
real memory storage / external services.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest


@pytest.fixture
def fake_manager():
    """A controllable fake memory manager with async stub methods.

    Each method is an async callable that can be re-pointed per test via
    ``monkeypatch.setattr(fake_manager, "method_name", async_func)``.
    Append ``_value`` to assert the value the route passed to a manager method.
    """
    return SimpleNamespace(
        list_memories=AsyncStub([]),
        get_concept_episode_counts_batch=AsyncStub({}),
        get_memory=AsyncStub(None),
        find_episodes_by_concept=AsyncStub([]),
        store_concept=AsyncStub(None),
        delete_memory=AsyncStub(True),
        save_memory=AsyncStub(None),
        search_memories=AsyncStub([]),
        search_concepts_data=AsyncStub([]),
        deduplicate_checkpoints=AsyncStub({"removed": 0}),
    )


class AsyncStub:
    """An async-safe stub: routes ``await`` this callable's result."""

    def __init__(self, return_value):
        self._return_value = return_value

    async def __call__(self, *args, **kwargs):
        return self._return_value


@pytest.fixture
async def client(fake_manager):
    """``httpx.AsyncClient`` over a minimal FastAPI app with the memory
    manager dependency overridden to yield *fake_manager*."""
    from fastapi import FastAPI

    import app.api.deps as deps
    from app.api.main import api_router
    from app.api.routes.memory.shared import get_memory_manager
    from app.models import User

    test_app = FastAPI(title="evo-api-test-memory")
    test_app.include_router(api_router)

    test_app.dependency_overrides[deps.oauth2_scheme] = lambda: "test-token"
    test_app.dependency_overrides[deps.oauth2_scheme_optional] = lambda: "test-token"

    async def _fake_user():
        return User(id=1, is_active=True, name="tester")

    test_app.dependency_overrides[deps.get_current_user] = _fake_user
    test_app.dependency_overrides[deps.get_current_user_optional] = _fake_user

    async def _ok_guest(*_a, **_kw):
        return None

    test_app.dependency_overrides[deps.verify_guest_access] = _ok_guest

    async def _fake_get_memory_manager():
        yield fake_manager

    test_app.dependency_overrides[get_memory_manager] = _fake_get_memory_manager

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30.0
    ) as c:
        yield c

    test_app.dependency_overrides.clear()
