# E2E 缺陷报告：test_route_init_spec

- **测试 ID**: `tests/e2e/test_07_health.py::TestServiceHealth::test_route_init_spec`
- **发现时间**: 2026-08-30T03:47:49.985143
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
.venv/lib/python3.11/site-packages/httpx/_transports/default.py:101: in map_httpcore_exceptions
    yield
.venv/lib/python3.11/site-packages/httpx/_transports/default.py:394: in handle_async_request
    resp = await self._pool.handle_async_request(req)
.venv/lib/python3.11/site-packages/httpcore/_async/connection_pool.py:256: in handle_async_request
    raise exc from None
.venv/lib/python3.11/site-packages/httpcore/_async/connection_pool.py:236: in handle_async_request
    response = await connection.handle_async_request(
.venv/lib/python3.11/site-packages/httpcore/_async/connection.py:101: in handle_async_request
    raise exc
.venv/lib/python3.11/site-packages/httpcore/_async/connection.py:78: in handle_async_request
    stream = await self._connect(request)
.venv/lib/python3.11/site-packages/httpcore/_async/connection.py:124: in _connect
    stream = await self._network_backend.connect_tcp(**kwargs)
.venv/lib/python3.11/site-packages/httpcore/_backends/auto.py:31: in connect_tcp
    return await self._backend.connect_tcp(
.venv/lib/python3.11/site-packages/httpcore/_backends/anyio.py:113: in connect_tcp
    with map_exceptions(exc_map):
../../../../.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/contextlib.py:158: in __exit__
    self.gen.throw(typ, value, traceback)
.venv/lib/python3.11/site-packages/httpcore/_exceptions.py:14: in map_exceptions
    raise to_exc(exc) from exc
E   httpcore.ConnectError: All connection attempts failed

The above exception was the direct cause of the following exception:
tests/e2e/test_07_health.py:52: in test_route_init_spec
    resp = await http_client.get("/api/v1/route/init")
.venv/lib/python3.11/site-packages/httpx/_client.py:1768: in get
    return await self.request(
.venv/lib/python3.11/site-packages/httpx/_client.py:1540: in request
    return await self.send(request, auth=auth, follow_redirects=follow_redirects)
app/infrastructure/llm/reasoning_patch.py:113: in _patched_httpx_send
    return await _original_httpx_send(self, request, **kwargs)
.venv/lib/python3.11/site-packages/httpx/_client.py:1629: in send
    response = await self._send_handling_auth(
.venv/lib/python3.11/site-packages/httpx/_client.py:1657: in _send_handling_auth
    response = await self._send_handling_redirects(
.venv/lib/python3.11/site-packages/httpx/_client.py:1694: in _send_handling_redirects
    response = await self._send_single_request(request)
.venv/lib/python3.11/site-packages/httpx/_client.py:1730: in _send_single_request
    response = await transport.handle_async_request(request)
.venv/lib/python3.11/site-packages/httpx/_transports/default.py:393: in handle_async_request
    with map_httpcore_exceptions():
../../../../.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/contextlib.py:158: in __exit__
    self.gen.throw(typ, value, traceback)
.venv/lib/python3.11/site-packages/httpx/_transports/default.py:118: in map_httpcore_exceptions
    raise mapped_exc(message) from exc
E   httpx.ConnectError: All connection attempts failed
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_07_health.py::TestServiceHealth::test_route_init_spec -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
