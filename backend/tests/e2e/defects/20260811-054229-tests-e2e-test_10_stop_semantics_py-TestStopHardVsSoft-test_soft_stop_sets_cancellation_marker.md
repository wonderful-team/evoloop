# E2E 缺陷报告：test_soft_stop_sets_cancellation_marker

- **测试 ID**: `tests/e2e/test_10_stop_semantics.py::TestStopHardVsSoft::test_soft_stop_sets_cancellation_marker`
- **发现时间**: 2026-08-11T05:42:29.808956
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_10_stop_semantics.py:108: in test_soft_stop_sets_cancellation_marker
    assert result.run_end_status in ("cancelled", "failed"), (
E   AssertionError: stop 后应观察到 cancelled/failed 终态，实际: done ({'type': 'run_end', 'thread_id': 'e2e-1c48157888d84a40', 'run_id': 'run-cf926b71', 'status': 'done', 'final_outcome': 'done'})
E   assert 'done' in ('cancelled', 'failed')
E    +  where 'done' = <tests.e2e.conftest.AgentLoopResult object at 0x1051a2510>.run_end_status
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_10_stop_semantics.py::TestStopHardVsSoft::test_soft_stop_sets_cancellation_marker -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
