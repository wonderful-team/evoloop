"""file facade 单元测试：action 分发、参数透传、未知 action、registry 面收敛。"""

from unittest.mock import AsyncMock

import pytest

from app.core.file.tools.facade import file


def _config():
    return {"configurable": {"thread_id": "t-1"}}


def test_registry_has_file_and_legacy_names_removed():
    import app.core.tools.registry as registry

    registry._ensure_scanned()
    tool_map = registry.get_tool_map()
    assert "file" in tool_map
    for legacy in ("read", "write", "edit", "list_dir", "move_file", "delete_file"):
        assert legacy not in tool_map, legacy


def test_facade_metadata():
    import app.core.tools.registry as registry

    registry._ensure_scanned()
    tool = registry.get_tool_map()["file"]
    assert tool._accepts_config is True
    assert tool.metadata.get("is_state_mutating") is True
    keys = tool.metadata.get("affected_path_keys") or []
    assert "path" in keys and "source" in keys and "destination" in keys


@pytest.mark.asyncio
async def test_read_dispatch_passthrough(monkeypatch):
    captured = {}

    async def _fake_read(**kwargs):
        captured.update(kwargs)
        return "READ-OK"

    monkeypatch.setattr("app.core.file.tools.facade._read_impl", AsyncMock(side_effect=_fake_read))
    out = await file(
        action="read", path="a.txt", start_line=2, end_line=9, config=_config()
    )
    assert out == "READ-OK"
    assert captured["path"] == "a.txt"
    assert captured["start_line"] == 2
    assert captured["end_line"] == 9


@pytest.mark.asyncio
async def test_write_dispatch_passthrough(monkeypatch):
    captured = {}

    async def _fake_write(**kwargs):
        captured.update(kwargs)
        return "WRITE-OK"

    monkeypatch.setattr("app.core.file.tools.facade._write_impl", AsyncMock(side_effect=_fake_write))
    out = await file(action="write", path="b.txt", content="hi", config=_config())
    assert out == "WRITE-OK"
    assert captured == {"path": "b.txt", "content": "hi", "config": _config()}


@pytest.mark.asyncio
async def test_edit_dispatch_passthrough(monkeypatch):
    captured = {}

    async def _fake_edit(**kwargs):
        captured.update(kwargs)
        return "EDIT-OK"

    monkeypatch.setattr("app.core.file.tools.facade._edit_impl", AsyncMock(side_effect=_fake_edit))
    out = await file(
        action="edit",
        path="c.py",
        target="old",
        replacement="new",
        allow_multiple=True,
        config=_config(),
    )
    assert out == "EDIT-OK"
    assert captured["target"] == "old"
    assert captured["replacement"] == "new"
    assert captured["allow_multiple"] is True


@pytest.mark.asyncio
async def test_list_move_delete_dispatch(monkeypatch):
    calls = {}

    async def _fake_list(**kwargs):
        calls["list"] = kwargs
        return "LIST-OK"

    async def _fake_move(**kwargs):
        calls["move"] = kwargs
        return "MOVE-OK"

    async def _fake_delete(**kwargs):
        calls["delete"] = kwargs
        return "DELETE-OK"

    monkeypatch.setattr("app.core.file.tools.facade._list_impl", AsyncMock(side_effect=_fake_list))
    monkeypatch.setattr("app.core.file.tools.facade._move_impl", AsyncMock(side_effect=_fake_move))
    monkeypatch.setattr("app.core.file.tools.facade._delete_impl", AsyncMock(side_effect=_fake_delete))

    assert await file(action="list", path="src/", tree=True, depth=2, config=_config()) == "LIST-OK"
    assert calls["list"]["tree"] is True and calls["list"]["depth"] == 2

    assert (
        await file(action="move", source="a.py", destination="b.py", config=_config())
        == "MOVE-OK"
    )
    assert calls["move"]["source"] == "a.py"

    assert await file(action="delete", path="x.txt", confirm=True, config=_config()) == "DELETE-OK"
    assert calls["delete"]["confirm"] is True


@pytest.mark.asyncio
async def test_unknown_action_rejected():
    out = await file(action="chmod", path="x", config=_config())
    assert out.startswith("Error: unknown file action 'chmod'")


@pytest.mark.asyncio
async def test_react_face_contains_file_not_legacy():
    import app.core.tools.registry as registry

    registry._ensure_scanned()
    tools = registry.get_agent_tools(
        "react", "app/core/engine/config/agent_main.yaml"
    )
    names = {t.name for t in tools}
    assert "file" in names
    assert "read" not in names and "write" not in names and "edit" not in names
