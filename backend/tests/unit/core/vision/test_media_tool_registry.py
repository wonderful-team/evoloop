"""Unit tests for media facade tool registration.

Verifies:
1. ``media`` facade is auto-registered in the tool registry.
2. Legacy ``image`` / ``video`` tool names no longer exist (merged into media).
3. ``media`` appears in the react agent face declared in agent_main.yaml.
4. Config injection metadata is set (``_accepts_config``).
"""

import inspect


def _registry():
    import app.core.tools.registry as registry

    registry._ensure_scanned()
    return registry.get_tool_map()


def test_media_registered():
    tool_map = _registry()
    assert "media" in tool_map


def test_legacy_image_video_removed():
    tool_map = _registry()
    assert "image" not in tool_map
    assert "video" not in tool_map


def test_facade_schema_params():
    tool = _registry()["media"]
    params = inspect.signature(tool.func).parameters
    assert "action" in params
    assert params["action"].default == "analyze"
    assert "kind" in params
    assert params["kind"].default is None


def test_config_injection_metadata():
    tool = _registry()["media"]
    assert tool._accepts_config is True
    assert tool.metadata.get("is_state_mutating") is True
    assert "source" in tool.metadata.get("affected_path_keys", [])


def test_react_face_contains_media():
    import app.core.tools.registry as registry

    registry._ensure_scanned()
    tools = registry.get_agent_tools(
        "react", "app/core/engine/config/agent_main.yaml"
    )
    names = {t.name for t in tools}
    assert "media" in names
    assert "image" not in names
    assert "video" not in names
