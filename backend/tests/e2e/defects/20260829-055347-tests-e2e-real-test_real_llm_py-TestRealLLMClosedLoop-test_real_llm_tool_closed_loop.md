# E2E 缺陷报告：test_real_llm_tool_closed_loop

- **测试 ID**: `tests/e2e/real/test_real_llm.py::TestRealLLMClosedLoop::test_real_llm_tool_closed_loop`
- **发现时间**: 2026-08-29T05:53:47.690820
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/real/test_real_llm.py:178: in test_real_llm_tool_closed_loop
    pytest.fail(
E   Failed: LLM 工具闭环运行未正常完成，status=failed, run_end={'type': 'run_end', 'thread_id': 'e2e-5f662720d6594520', 'run_id': 'run-0e419691', 'status': 'failed', 'final_outcome': 'failed'}
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/real/test_real_llm.py::TestRealLLMClosedLoop::test_real_llm_tool_closed_loop -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
