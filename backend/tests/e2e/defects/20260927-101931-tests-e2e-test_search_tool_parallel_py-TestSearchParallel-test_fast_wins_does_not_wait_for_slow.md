# E2E 缺陷报告：test_fast_wins_does_not_wait_for_slow

- **测试 ID**: `tests/e2e/test_search_tool_parallel.py::TestSearchParallel::test_fast_wins_does_not_wait_for_slow`
- **发现时间**: 2026-09-27T10:19:31.527115
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_search_tool_parallel.py:50: in test_fast_wins_does_not_wait_for_slow
    assert slow.cancelled, "慢引擎任务应被取消"
E   AssertionError: 慢引擎任务应被取消
E   assert False
E    +  where False = <tests.e2e.test_search_tool_parallel._EngineStub object at 0x123ee2240>.cancelled
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_search_tool_parallel.py::TestSearchParallel::test_fast_wins_does_not_wait_for_slow -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
