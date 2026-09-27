# E2E 缺陷报告：test_connect_call_tools_resources_prompts

- **测试 ID**: `tests/e2e/test_mcp_chain.py::TestMcpToolCallChain::test_connect_call_tools_resources_prompts`
- **发现时间**: 2026-08-05T23:18:21.638184
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_mcp_chain.py:85: in test_connect_call_tools_resources_prompts
    assert "add" in by_name, f"add 工具未加载: {list(by_name)}"
E   AssertionError: add 工具未加载: ['mcp__mini_inproc_1a06b247__add', 'mcp__mini_inproc_1a06b247__echo']
E   assert 'add' in {'mcp__mini_inproc_1a06b247__add': <app.core.tools.base.EvoLoopTool object at 0x105d73e10>, 'mcp__mini_inproc_1a06b247__echo': <app.core.tools.base.EvoLoopTool object at 0x106bfe590>}
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
