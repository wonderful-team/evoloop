"""Unit tests for image/video facade tool registration.

Verifies:
1. ``image`` and ``video`` tools are auto-registered in the tool registry.
2. Legacy ``analyze_image`` tool name no longer exists.
3. Both tools appear in the react agent face declared in agent_main.yaml.
4. Config injection metadata is set (``_accepts_config``).
"""

import inspect


def _registry():
    import app.core.tools.registry as registry

    registry._ensure_scanned()
    return registry.get_tool_map()


def test_image_and_video_registered():
    tool_map = _registry()
    assert "image" in tool_map
    assert "video" in tool_map


def test_legacy_analyze_image_removed():
    tool_map = _registry()
    assert "analyze_image" not in tool_map


def test_facade_schema_params():
    tool_map = _registry()
    for name in ("image", "video"):
        tool = tool_map[name]
        params = inspect.signature(tool.func).parameters
        assert "action" in params
        assert params["action"].default == "analyze"


def test_config_injection_metadata():
    tool_map = _registry()
    for name in ("image", "video"):
        tool = tool_map[name]
        assert tool._accepts_config is True
        assert tool.metadata.get("is_state_mutating") is True
        assert "source" in tool.metadata.get("affected_path_keys", [])


def test_react_face_contains_image_video():
    import app.core.tools.registry as registry

    registry._ensure_scanned()
    tools = registry.get_agent_tools(
        "react", "app/core/engine/config/agent_main.yaml"
    )
    names = {t.name for t in tools}
    assert "image" in names
    assert "video" in names
    assert "analyze_image" not in names


def test_facade_not_multimodal_gated():
    """generate 动作不依赖 VISION_MODEL，因此不应标 is_multimodal=True
    （否则 VISION_MODEL 未配置时整个工具会被 ToolManager 过滤掉）。"""
    tool_map = _registry()
    for name in ("image", "video"):
        tool = tool_map[name]
        assert tool.metadata.get("is_multimodal") is not True
