# E2E 缺陷报告：test_real_tool_run_via_agent[dangerous-command-blocked]

- **测试 ID**: `tests/e2e/real/test_real_tools.py::TestRealToolExecution::test_real_tool_run_via_agent[dangerous-command-blocked]`
- **发现时间**: 2026-08-29T15:32:53.155429
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/real/test_real_tools.py:249: in test_real_tool_run_via_agent
    assert found_marker, (
E   AssertionError: 工具输出中未包含期望标记 'Security Error', tool_outputs=[{"id": "770d2974-138a-4466-b2ce-74008d3b0737", "thread_id": "e2e-778b79d9f6604123", "run_id": "run-12dc5923", "role": "tool", "category": "tool_output", "content": "", "content_type": "text", "thinking": null, "tool_calls": null, "tool_name": "execute_command", "tool_call_id": "call_662uexg7u5ycueslfzg3z2u5", "input": {"command": "whoami && id && pwd && which rm && rm --version 2>&1 | head -3", "timeout": 15}, "tool_meta": {"display_name": "正在运行命令 'whoami && id && pwd && which rm && rm --versio
E   assert False
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/real/test_real_tools.py::TestRealToolExecution::test_real_tool_run_via_agent[dangerous-command-blocked] -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
