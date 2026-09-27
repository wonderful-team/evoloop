"""Integration tests for the /tools API routes (app/api/routes/tools.py)."""

from __future__ import annotations

from types import SimpleNamespace


def _make_tool(name="test-tool", desc="A test tool"):
    return SimpleNamespace(
        name=name,
        description=desc,
        args_schema=None,
    )


class TestListRuntimeTools:
    async def test_empty(self, client, monkeypatch):
        from app.core.tools.registry import REGISTRY

        monkeypatch.setattr(REGISTRY, "get_runtime_tools", lambda: [])
        resp = await client.get("/tools/runtime")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_tools(self, client, monkeypatch):
        from app.core.tools.registry import REGISTRY

        monkeypatch.setattr(
            REGISTRY, "get_runtime_tools", lambda: [_make_tool("rt-1")]
        )
        resp = await client.get("/tools/runtime")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "rt-1"


class TestListAllTools:
    async def test_empty(self, client, monkeypatch):
        from app.core.tools.manager import tool_manager
        from app.core.tools.registry import REGISTRY

        async def _get_all():
            return []

        monkeypatch.setattr(tool_manager, "get_all_capabilities", _get_all)
        monkeypatch.setattr(REGISTRY, "get_runtime_tools", lambda: [])
        resp = await client.get("/tools")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_all_tools(self, client, monkeypatch):
        from app.core.tools.manager import tool_manager
        from app.core.tools.registry import REGISTRY

        t1 = _make_tool("bash", "Run bash")
        t2 = _make_tool("read", "Read file")

        async def _get_all():
            return [t1, t2]

        monkeypatch.setattr(tool_manager, "get_all_capabilities", _get_all)
        monkeypatch.setattr(
            REGISTRY, "get_runtime_tools", lambda: [_make_tool("bash")]
        )
        resp = await client.get("/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {t["name"] for t in data}
        assert "bash" in names
        assert "read" in names
        bash_info = next(t for t in data if t["name"] == "bash")
        assert bash_info["is_runtime"] is True

    async def test_tools_with_args_schema(self, client, monkeypatch):
        from app.core.tools.manager import tool_manager
        from app.core.tools.registry import REGISTRY

        schema_cls = type(
            "FakeSchema",
            (),
            {"model_json_schema": staticmethod(lambda: {"type": "object"})},
        )
        t = SimpleNamespace(
            name="echo",
            description="Echo",
            args_schema=schema_cls,
        )

        async def _get_all():
            return [t]

        monkeypatch.setattr(tool_manager, "get_all_capabilities", _get_all)
        monkeypatch.setattr(REGISTRY, "get_runtime_tools", lambda: [])
        resp = await client.get("/tools")
        assert resp.status_code == 200
        assert resp.json()[0]["args_schema"] == {"type": "object"}
