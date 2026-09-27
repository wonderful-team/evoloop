"""ToolsManager 装配单元测试：native 裁剪 + server 名归一化。

（allowlist 过滤用例已于 S4 随 mcp_allowlist 字段删除核销（C6）；
包可见性契约见 test_capability_packages.py。）"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.engine.capability_profiles import CapabilityProfile
from app.core.tools.manager import ToolManager


def _tool(name: str):
    t = type("T", (), {})
    t.name = name
    t.metadata = {}
    return t


def test_server_of_mcp_tool_parses_server():
    assert ToolManager._server_of_mcp_tool("mcp__capability_matrix__list_goods") == "capability_matrix"
    assert ToolManager._server_of_mcp_tool("mcp__filesystem__read") == "filesystem"
    assert ToolManager._server_of_mcp_tool("bash") == ""


def test_server_name_normalization():
    # 工具名内嵌下划线形式，注册名含连字符——归一化后必须匹配（包面过滤依赖）
    server = ToolManager._server_of_mcp_tool("mcp__capability_matrix__list_goods")
    assert server.replace("-", "_") in {s.replace("-", "_") for s in ["capability-matrix"]}


@pytest.mark.asyncio
async def test_no_profile_keeps_full_surface():
    """无域 profile（桌面/ambiguous）→ 全量注入，零回归。"""
    fake_mcp = [_tool("mcp__filesystem__read"), _tool("mcp__capability_matrix__post")]

    with (
        patch(
            "app.core.tools.registry.get_agent_tools",
            return_value=[_tool("bash"), _tool("question")],
        ),
        patch(
            "app.core.mcp.mcp_client_manager.aget_all_tools",
            new=AsyncMock(return_value=fake_mcp),
        ),
        patch.object(ToolManager, "_resolve_domain_profile", return_value=None),
    ):
        tools = await ToolManager().get_agent_tools("react", state=object())

    assert {t.name for t in tools} == {
        "bash",
        "question",
        "mcp__filesystem__read",
        "mcp__capability_matrix__post",
    }


@pytest.mark.asyncio
async def test_native_tools_pruned_by_profile():
    """native_tools 白名单做减法：profile 外的 native 工具不出现。"""
    with (
        patch(
            "app.core.tools.registry.get_agent_tools",
            return_value=[_tool("bash"), _tool("edit"), _tool("question")],
        ),
        patch(
            "app.core.mcp.mcp_client_manager.aget_all_tools",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(
            ToolManager,
            "_resolve_domain_profile",
            return_value=CapabilityProfile(domain="mall_ops", native_tools=["question"]),
        ),
    ):
        tools = await ToolManager().get_agent_tools("react", state=object())

    assert [t.name for t in tools] == ["question"]
