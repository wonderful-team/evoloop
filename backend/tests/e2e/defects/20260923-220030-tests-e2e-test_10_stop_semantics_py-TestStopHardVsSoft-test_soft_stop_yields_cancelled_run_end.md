# E2E 缺陷报告：test_soft_stop_yields_cancelled_run_end

- **测试 ID**: `tests/e2e/test_10_stop_semantics.py::TestStopHardVsSoft::test_soft_stop_yields_cancelled_run_end`
- **发现时间**: 2026-09-23T22:00:30.523495
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_10_stop_semantics.py:166: in test_soft_stop_yields_cancelled_run_end
    assert result.run_end_status == "cancelled", (
E   AssertionError: 软停止后 run_end 必须精确为 cancelled（十四.2：run_scope 发布 end_run(status='cancelled')），实际: failed ({'type': 'run_end', 'thread_id': 'e2e-c9f30104e7414c80', 'run_id': 'run-f1a15e4a', 'status': 'failed', 'final_outcome': 'failed'})
E   assert 'failed' == 'cancelled'
E     - cancelled
E     + failed
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_10_stop_semantics.py::TestStopHardVsSoft::test_soft_stop_yields_cancelled_run_end -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
