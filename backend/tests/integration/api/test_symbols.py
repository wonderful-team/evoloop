"""Integration tests for the symbols routes (app/api/routes/symbols.py)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.main import api_router


@pytest.fixture
def symbols_client():
    """Create a client with get_db dependency overridden."""
    import app.api.deps as deps
    from app.api.deps import get_db
    from app.models import User

    test_app = FastAPI(title="evo-api-test")
    test_app.include_router(api_router)
    test_app.dependency_overrides[deps.oauth2_scheme] = lambda: "test-token"
    test_app.dependency_overrides[deps.oauth2_scheme_optional] = lambda: "test-token"

    async def _fake_user():
        return User(id=1, is_active=True, name="tester")

    test_app.dependency_overrides[deps.get_current_user] = _fake_user
    test_app.dependency_overrides[deps.get_current_user_optional] = _fake_user

    async def _ok_guest(
        _current_user=None, _x_guest_id=None, _guest_id=None, _token=None,
    ):
        return None

    test_app.dependency_overrides[deps.verify_guest_access] = _ok_guest

    return test_app, get_db


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, scalars=None):
        self._scalars = scalars or []

    def scalars(self):
        return _FakeScalars(self._scalars)


class TestSearchSymbols:
    async def test_no_repos(self, symbols_client):
        test_app, get_db = symbols_client

        class FakeDB:
            def execute(self, stmt):
                return _FakeResult([])

        test_app.dependency_overrides[get_db] = lambda: FakeDB()

        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=30.0
        ) as c:
            resp = await c.get("/projects/1/symbols?q=test")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_with_results(self, symbols_client):
        test_app, get_db = symbols_client

        class FakeFile:
            path = "src/main.py"

        class FakeEntity:
            id = 1
            name = "MyClass"
            full_name = "pkg.MyClass"
            type = "class"
            file = FakeFile()
            start_line = 10
            end_line = 50

        call_count = 0

        class FakeDB:
            def execute(self, stmt):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return _FakeResult([1])
                return _FakeResult([FakeEntity()])

        test_app.dependency_overrides[get_db] = lambda: FakeDB()

        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=30.0
        ) as c:
            resp = await c.get("/projects/1/symbols?q=MyClass")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "MyClass"
        assert data[0]["file_path"] == "src/main.py"

    async def test_no_repos_returns_empty(self, symbols_client):
        test_app, get_db = symbols_client

        call_count = 0

        class FakeDB:
            def execute(self, stmt):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return _FakeResult([1])
                return _FakeResult([])

        test_app.dependency_overrides[get_db] = lambda: FakeDB()

        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=30.0
        ) as c:
            resp = await c.get("/projects/1/symbols?q=anything")
        assert resp.status_code == 200
        assert resp.json() == []


class TestProjectRelations:
    async def test_no_repos(self, symbols_client):
        test_app, get_db = symbols_client

        class FakeDB:
            def execute(self, stmt):
                return _FakeResult([])

        test_app.dependency_overrides[get_db] = lambda: FakeDB()

        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=30.0
        ) as c:
            resp = await c.get("/projects/1/relations")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_with_relations(self, symbols_client):
        test_app, get_db = symbols_client

        class FakeFile:
            path = "src/a.py"

        class FakeSource:
            id = 1
            name = "func_a"
            file = FakeFile()

        class FakeTarget:
            id = 2
            name = "func_b"
            file = FakeFile()

        class FakeRelation:
            id = 10
            source_entity_id = 1
            target_entity_id = 2
            source_entity = FakeSource()
            target_entity = FakeTarget()
            target_name = "func_b"
            relation_type = "calls"

        call_count = 0

        class FakeDB:
            def execute(self, stmt):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return _FakeResult([1])
                return _FakeResult([FakeRelation()])

        test_app.dependency_overrides[get_db] = lambda: FakeDB()

        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=30.0
        ) as c:
            resp = await c.get("/projects/1/relations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["source_name"] == "func_a"
        assert data[0]["target_name"] == "func_b"
        assert data[0]["relation_type"] == "calls"

    async def test_entities_with_none_files(self, symbols_client):
        test_app, get_db = symbols_client

        class FakeSource:
            id = 1
            name = "func_a"
            file = None

        class FakeTarget:
            id = 2
            name = "func_b"
            file = None

        class FakeRelation:
            id = 10
            source_entity_id = 1
            target_entity_id = 2
            source_entity = FakeSource()
            target_entity = FakeTarget()
            target_name = "func_b"
            relation_type = "calls"

        call_count = 0

        class FakeDB:
            def execute(self, stmt):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return _FakeResult([1])
                return _FakeResult([FakeRelation()])

        test_app.dependency_overrides[get_db] = lambda: FakeDB()

        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=30.0
        ) as c:
            resp = await c.get("/projects/1/relations")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["source_file_path"] == ""
        assert data[0]["target_file_path"] is None
