# E2E 缺陷报告：test_new_command_cancels_previous_worker_run

- **测试 ID**: `tests/e2e/test_08_voice_state_machine.py::TestNewCommandHardKill::test_new_command_cancels_previous_worker_run`
- **发现时间**: 2026-08-06T05:58:49.660899
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_08_voice_state_machine.py:201: in test_new_command_cancels_previous_worker_run
    assert result.run_end_status == "cancelled", (
E   AssertionError: NEW_COMMAND 节点转移应硬掐断旧任务（loop.py:67-76 pop_previous_task + old_task.cancel()），旧 run_end 必须为 cancelled，实际: quota_exhausted ({'type': 'run_end', 'thread_id': 'e2e-f4a0d4d5ce694d98', 'run_id': None, 'status': 'quota_exhausted', 'final_outcome': None})
E   assert 'quota_exhausted' == 'cancelled'
E     - cancelled
E     + quota_exhausted
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_08_voice_state_machine.py::TestNewCommandHardKill::test_new_command_cancels_previous_worker_run -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
