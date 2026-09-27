# E2E 缺陷报告：test_attachment_md5_mismatch_returns_error

- **测试 ID**: `tests/e2e/test_12_a2a.py::TestA2AAttachmentValidation::test_attachment_md5_mismatch_returns_error`
- **发现时间**: 2026-08-06T03:36:22.854780
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_12_a2a.py:654: in test_attachment_md5_mismatch_returns_error
    await _wait_for_send_agent_task_or_skip(
tests/e2e/test_12_a2a.py:156: in _wait_for_send_agent_task_or_skip
    return await _wait_for_tool_call(
tests/e2e/test_12_a2a.py:113: in _wait_for_tool_call
    await wait_until(
tests/e2e/conftest.py:83: in wait_until
    last_value = await predicate()
tests/e2e/test_12_a2a.py:103: in _found
    messages = await _get_messages(
tests/e2e/test_12_a2a.py:85: in _get_messages
    resp.raise_for_status()
.venv/lib/python3.11/site-packages/httpx/_models.py:829: in raise_for_status
    raise HTTPStatusError(message, request=request, response=self)
E   httpx.HTTPStatusError: Server error '502 Bad Gateway' for url 'http://127.0.0.1:20160/api/v1/conversations/e2e-04280afc403c413c/messages?include_tool_calls=true'
E   For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/502
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_12_a2a.py::TestA2AAttachmentValidation::test_attachment_md5_mismatch_returns_error -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
