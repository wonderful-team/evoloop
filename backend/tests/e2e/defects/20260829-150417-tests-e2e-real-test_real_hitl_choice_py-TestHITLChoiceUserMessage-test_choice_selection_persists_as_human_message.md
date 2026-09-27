# E2E 缺陷报告：test_choice_selection_persists_as_human_message

- **测试 ID**: `tests/e2e/real/test_real_hitl_choice.py::TestHITLChoiceUserMessage::test_choice_selection_persists_as_human_message`
- **发现时间**: 2026-08-29T15:04:17.593776
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/real/test_real_hitl_choice.py:140: in test_choice_selection_persists_as_human_message
    await collect_sse_until(
tests/e2e/conftest.py:186: in collect_sse_until
    await _read_sse_stream(client, url, _handler, timeout=timeout)
tests/e2e/conftest.py:128: in _read_sse_stream
    raise TimeoutError(f"SSE 读取超时({timeout}s)")
E   TimeoutError: SSE 读取超时(200.0s)

During handling of the above exception, another exception occurred:
tests/e2e/real/test_real_hitl_choice.py:149: in test_choice_selection_persists_as_human_message
    pytest.fail(f"choice 提交后未在窗口内收到 run_end: {exc}")
E   Failed: choice 提交后未在窗口内收到 run_end: SSE 读取超时(200.0s)
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/real/test_real_hitl_choice.py::TestHITLChoiceUserMessage::test_choice_selection_persists_as_human_message -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
