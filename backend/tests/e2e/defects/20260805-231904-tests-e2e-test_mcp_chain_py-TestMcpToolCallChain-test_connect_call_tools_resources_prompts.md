# E2E 缺陷报告：test_connect_call_tools_resources_prompts

- **测试 ID**: `tests/e2e/test_mcp_chain.py::TestMcpToolCallChain::test_connect_call_tools_resources_prompts`
- **发现时间**: 2026-08-05T23:19:04.773682
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_mcp_chain.TestMcpToolCallChain object at 0x107413250>

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
    
>           resources = await mcp_client_manager.list_resources(name)

tests/e2e/test_mcp_chain.py:96: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <app.core.mcp.client.manager.McpClientManager object at 0x108e3d910>
server_name = 'mini-inproc-3ed0fd6f'

    async def list_resources(self, server_name: str) -> list[McpResource]:
        """
        List available resources from a server.
    
        Args:
            server_name: Server name
    
        Returns:
            List of resource info dicts
        """
        if await self.ensure_connected(server_name):
            feature = self._resources_feature.get(server_name)
            if feature:
                resources = feature.get_resources()
>               return [
                    McpResource(
                        uri=r.uri,
                        name=r.name,
                        mimeType=r.mimeType,
                        description=r.description,
                    )
                    for r in resources
                ]

app/core/mcp/client/manager.py:382: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

.0 = <list_iterator object at 0x10a672ec0>

    return [
>       McpResource(
            uri=r.uri,
            name=r.name,
            mimeType=r.mimeType,
            description=r.description,
        )
        for r in resources
    ]
E   pydantic_core._pydantic_core.ValidationError: 1 validation error for McpResource
E   uri
E     Input should be a valid string [type=string_type, input_value=AnyUrl('greeting://default'), input_type=AnyUrl]
E       For further information visit https://errors.pydantic.dev/2.12/v/string_type

app/core/mcp/client/manager.py:383: ValidationError
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_mcp_chain.py::TestMcpToolCallChain::test_connect_call_tools_resources_prompts -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
