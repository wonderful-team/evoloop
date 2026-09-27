# E2E 缺陷报告：test_progress_query_does_not_kill_old_worker

- **测试 ID**: `tests/e2e/test_10_stop_semantics.py::TestProgressQuerySemantics::test_progress_query_does_not_kill_old_worker`
- **发现时间**: 2026-08-15T05:14:09.732243
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_10_stop_semantics.py:366: in test_progress_query_does_not_kill_old_worker
    assert result.run_end_status == "done", (
E   AssertionError: 旧任务应自然终态 done（进度询问不应掐断旧 Worker），实际: failed ({'type': 'run_end', 'thread_id': 'e2e-54f115eb6e2c42d3', 'run_id': 'run-b844502c', 'status': 'failed', 'final_outcome': 'failed'})
E   assert 'failed' == 'done'
E     - done
E     + failed
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_10_stop_semantics.py::TestProgressQuerySemantics::test_progress_query_does_not_kill_old_worker -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
