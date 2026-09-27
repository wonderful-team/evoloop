# E2E 缺陷报告：test_real_run_full_event_chain

- **测试 ID**: `tests/e2e/test_03_engine.py::TestRealAgentRun::test_real_run_full_event_chain`
- **发现时间**: 2026-09-24T04:01:36.666459
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_03_engine.py:131: in test_real_run_full_event_chain
    assert "token" in event_names, f"缺少 token 流式事件: {event_names}"
E   AssertionError: 缺少 token 流式事件: ['activity', 'message', 'run_start', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'thinking', 'progress', 'message', 'task_created', 'agent_state', 'task_started', 'task_output', 'agent_state', 'task_completed', 'agent_state', 'progress', 'message', 'message', 'message', 'message', 'session_completed', 'run_end']
E   assert 'token' in ['activity', 'message', 'run_start', 'thinking', 'thinking', 'thinking', ...]
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_03_engine.py::TestRealAgentRun::test_real_run_full_event_chain -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
