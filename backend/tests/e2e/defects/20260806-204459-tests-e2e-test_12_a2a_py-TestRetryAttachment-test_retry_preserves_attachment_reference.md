# E2E 缺陷报告：test_retry_preserves_attachment_reference

- **测试 ID**: `tests/e2e/test_12_a2a.py::TestRetryAttachment::test_retry_preserves_attachment_reference`
- **发现时间**: 2026-08-06T20:44:59.495861
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_12_a2a.py:468: in test_retry_preserves_attachment_reference
    messages = await _get_messages(http_client, thread_id)
tests/e2e/test_12_a2a.py:85: in _get_messages
    resp.raise_for_status()
.venv/lib/python3.11/site-packages/httpx/_models.py:829: in raise_for_status
    raise HTTPStatusError(message, request=request, response=self)
E   httpx.HTTPStatusError: Server error '500 Internal Server Error' for url 'http://127.0.0.1:20160/api/v1/conversations/e2e-e39870bf240c4173/messages?include_tool_calls=false'
E   For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_12_a2a.py::TestRetryAttachment::test_retry_preserves_attachment_reference -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
