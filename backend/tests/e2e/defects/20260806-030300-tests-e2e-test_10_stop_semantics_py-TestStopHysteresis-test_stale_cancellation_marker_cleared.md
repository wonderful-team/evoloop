# E2E 缺陷报告：test_stale_cancellation_marker_cleared

- **测试 ID**: `tests/e2e/test_10_stop_semantics.py::TestStopHysteresis::test_stale_cancellation_marker_cleared`
- **发现时间**: 2026-08-06T03:03:00.882452
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_10_stop_semantics.py:298: in test_stale_cancellation_marker_cleared
    assert result2.run_end_status in (
E   AssertionError: 新运行应正常完成或失败，实际: quota_exhausted
E   assert 'quota_exhausted' in ('done', 'failed')
E    +  where 'quota_exhausted' = <tests.e2e.conftest.AgentLoopResult object at 0x1679fb0d0>.run_end_status
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_10_stop_semantics.py::TestStopHysteresis::test_stale_cancellation_marker_cleared -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
