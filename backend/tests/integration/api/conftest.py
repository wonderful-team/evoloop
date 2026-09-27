# ruff: noqa: ARG001
"""Shared test harness for API route integration tests.

Builds a minimal FastAPI app from ``app.api.main.api_router`` WITHOUT the heavy
lifespan / middleware, and exposes an ``httpx.AsyncClient`` (ASGITransport) so
tests exercise the real routing layer (path params, query params, request body
parsing, response envelope, HTTP status codes) while mocking service boundaries
via ``monkeypatch`` at the route-module level.

Auth (``get_current_user`` / ``get_current_user_optional`` / ``TokenDep``) is
overridden to an anonymous authenticated user so tests don't hit IdentityService.
Individual tests can re-override for 401/403 paths as needed.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import httpx
import pytest

# --- Test-scoped SQLite DB so DB-backed helpers are exercised for real. ---
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="evo_api_integration_"))
_TEST_DB_PATH = _TEST_DB_DIR / "test.db"

os.environ.setdefault("SQLITE_PATH", str(_TEST_DB_PATH))
os.environ.setdefault("EMBEDDED_MODE", "true")
os.environ.setdefault("MULTI_TENANT_MODE", "false")


@pytest.fixture(scope="session")
def api_test_db_path() -> Path:
    return _TEST_DB_PATH


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """httpx.AsyncClient wired to a minimal FastAPI app over the api_router."""
    from fastapi import FastAPI

    import app.api.deps as deps
    from app.api.main import api_router
    from app.models import User

    test_app = FastAPI(title="evo-api-test")
    test_app.include_router(api_router)

    # --- Override auth dependencies to an anonymous authenticated user. ---
    # Satisfy the OAuth2PasswordBearer security scheme without a real token.
    test_app.dependency_overrides[deps.oauth2_scheme] = lambda: "test-token"
    test_app.dependency_overrides[deps.oauth2_scheme_optional] = lambda: "test-token"

    async def _fake_user():
        return User(id=1, is_active=True, name="tester")

    test_app.dependency_overrides[deps.get_current_user] = _fake_user
    test_app.dependency_overrides[deps.get_current_user_optional] = _fake_user

    # guest access is skipped because current_user is present
    async def _ok_guest(
        current_user=None,
        x_guest_id=None,
        guest_id=None,
        token=None,
    ):
        return None

    test_app.dependency_overrides[deps.verify_guest_access] = _ok_guest

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30.0
    ) as c:
        yield c

    test_app.dependency_overrides.clear()
