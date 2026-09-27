# E2E 缺陷报告：test_barge_in_during_tts_does_not_kill_worker

- **测试 ID**: `tests/e2e/test_08_voice_state_machine.py::TestBargeInAgentRun::test_barge_in_during_tts_does_not_kill_worker`
- **发现时间**: 2026-09-23T22:21:57.324994
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_08_voice_state_machine.py:69: in test_barge_in_during_tts_does_not_kill_worker
    result = await observe_agent_run(
tests/e2e/conftest.py:540: in observe_agent_run
    await _read_sse_stream(
tests/e2e/conftest.py:128: in _read_sse_stream
    raise TimeoutError(f"SSE 读取超时({timeout}s)")
E   TimeoutError: SSE 读取超时(120.0s)
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_08_voice_state_machine.py::TestBargeInAgentRun::test_barge_in_during_tts_does_not_kill_worker -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
