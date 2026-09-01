"""阶段29：MCP 客户端链路端到端测试。

覆盖两条真实路径：
1. 管理 API（前端 UI 调用）：POST /api/v1/mcp/server 注册 → connect → list →
   delete，验证 ConnectionResult.tools_count、summary.status/tools_count。
2. 工具调用链（Agent 路径）：进程内 McpClientManager.connect → get_tools →
   ainvoke 远程工具，验证 add/echo 真实执行、resources/prompts 特性初始化。

MCP 服务器用自包含极简 stdio 服务（tests/e2e/mcp_servers/mini_mcp_server.py），
仅依赖 mcp 包，由客户端传输层以子进程方式拉起（与生产 stdio 传输一致）。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_SERVER_PATH = Path(__file__).parent / "mcp_servers" / "mini_mcp_server.py"


def _server_args() -> list[str]:
    return [str(_SERVER_PATH)]


class TestMcpManagementApi:
    """E2E-SC-029: 前端 MCP 管理 API 全链路（注册/连接/列表/删除）。"""

    @pytest.mark.timeout(120)
    async def test_add_connect_list_delete(self, http_client) -> None:
        name = f"mini-e2e-{uuid.uuid4().hex[:8]}"
        try:
            resp = await http_client.post(
                "/api/v1/mcp/server",
                json={"name": name, "command": sys.executable, "args": _server_args(), "env": {}},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body.get("success") is True, body
            assert body.get("tools_count", 0) >= 2, f"应列出 2 个工具: {body}"

            listed = await http_client.get("/api/v1/mcp/servers")
            assert listed.status_code == 200
            entries = listed.json()
            entry = next((s for s in entries if s.get("name") == name), None)
            assert entry is not None, f"服务器未出现在列表中: {name}"
            assert entry.get("status") == "connected", entry
            assert entry.get("tools_count", 0) >= 2, entry

            conn = await http_client.post(f"/api/v1/mcp/server/{name}/connect")
            assert conn.status_code == 200, conn.text
            assert conn.json().get("tools_count", 0) >= 2
        finally:
            await http_client.delete(f"/api/v1/mcp/server/{name}")


class TestMcpToolCallChain:
    """E2E-SC-029: Agent 工具调用链（连接→取工具→真实调用→资源/提示）。"""

    @pytest.mark.timeout(120)
    async def test_connect_call_tools_resources_prompts(self) -> None:
        from app.core.mcp import mcp_client_manager
        from app.core.mcp.config import McpServerConfig, TransportType

        name = f"mini-inproc-{uuid.uuid4().hex[:8]}"
        config = McpServerConfig(
            name=name,
            transport=TransportType.STDIO,
            command=sys.executable,
            args=_server_args(),
            env={},
            enabled=True,
        )
        try:
            result = await mcp_client_manager.connect(config)
            assert result.success, f"连接失败: {result.error}"
            assert result.tools_count >= 2, f"工具数异常: {result.tools_count}"

            tools = await mcp_client_manager.get_tools(name)
            by_name = {t.name: t for t in tools}
            add_tool = next((t for n, t in by_name.items() if n.endswith("__add")), None)
            echo_tool = next((t for n, t in by_name.items() if n.endswith("__echo")), None)
            assert add_tool is not None, f"add 工具未加载: {list(by_name)}"
            assert echo_tool is not None, f"echo 工具未加载: {list(by_name)}"

            out = await add_tool.ainvoke({"a": 2, "b": 40})
            assert "42" in str(out), f"add 远程调用结果异常: {out!r}"

            out2 = await echo_tool.ainvoke({"text": "hello-mcp"})
            assert "echo:hello-mcp" in str(out2), f"echo 远程调用结果异常: {out2!r}"

            resources = await mcp_client_manager.list_resources(name)
            assert any("greeting" in r.uri for r in resources), resources

            prompts = await mcp_client_manager.list_prompts(name)
            assert any(p.name == "summarize" for p in prompts), prompts
        finally:
            await mcp_client_manager.disconnect(name)
