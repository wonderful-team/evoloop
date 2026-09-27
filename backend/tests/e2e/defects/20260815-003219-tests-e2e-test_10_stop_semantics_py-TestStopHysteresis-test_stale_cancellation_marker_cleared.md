# E2E 缺陷报告：test_stale_cancellation_marker_cleared

- **测试 ID**: `tests/e2e/test_10_stop_semantics.py::TestStopHysteresis::test_stale_cancellation_marker_cleared`
- **发现时间**: 2026-08-15T00:32:19.157188
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
.venv/lib/python3.11/site-packages/httpx/_transports/default.py:101: in map_httpcore_exceptions
    yield
.venv/lib/python3.11/site-packages/httpx/_transports/default.py:271: in __aiter__
    async for part in self._httpcore_stream:
.venv/lib/python3.11/site-packages/httpcore/_async/connection_pool.py:407: in __aiter__
    raise exc from None
.venv/lib/python3.11/site-packages/httpcore/_async/connection_pool.py:403: in __aiter__
    async for part in self._stream:
.venv/lib/python3.11/site-packages/httpcore/_async/http11.py:342: in __aiter__
    raise exc
.venv/lib/python3.11/site-packages/httpcore/_async/http11.py:334: in __aiter__
    async for chunk in self._connection._receive_response_body(**kwargs):
.venv/lib/python3.11/site-packages/httpcore/_async/http11.py:203: in _receive_response_body
    event = await self._receive_event(timeout=timeout)
.venv/lib/python3.11/site-packages/httpcore/_async/http11.py:213: in _receive_event
    with map_exceptions({h11.RemoteProtocolError: RemoteProtocolError}):
../../../../.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/contextlib.py:158: in __exit__
    self.gen.throw(typ, value, traceback)
.venv/lib/python3.11/site-packages/httpcore/_exceptions.py:14: in map_exceptions
    raise to_exc(exc) from exc
E   httpcore.RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)

The above exception was the direct cause of the following exception:
tests/e2e/test_10_stop_semantics.py:294: in test_stale_cancellation_marker_cleared
    result2 = await sse_task2
tests/e2e/conftest.py:540: in observe_agent_run
    await _read_sse_stream(
tests/e2e/conftest.py:124: in _read_sse_stream
    line = await anext(line_iter)
.venv/lib/python3.11/site-packages/httpx/_models.py:1031: in aiter_lines
    async for text in self.aiter_text():
.venv/lib/python3.11/site-packages/httpx/_models.py:1018: in aiter_text
    async for byte_content in self.aiter_bytes():
.venv/lib/python3.11/site-packages/httpx/_models.py:997: in aiter_bytes
    async for raw_bytes in self.aiter_raw():
.venv/lib/python3.11/site-packages/httpx/_models.py:1055: in aiter_raw
    async for raw_stream_bytes in self.stream:
.venv/lib/python3.11/site-packages/httpx/_client.py:176: in __aiter__
    async for chunk in self._stream:
.venv/lib/python3.11/site-packages/httpx/_transports/default.py:270: in __aiter__
    with map_httpcore_exceptions():
../../../../.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/contextlib.py:158: in __exit__
    self.gen.throw(typ, value, traceback)
.venv/lib/python3.11/site-packages/httpx/_transports/default.py:118: in map_httpcore_exceptions
    raise mapped_exc(message) from exc
E   httpx.RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)
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
