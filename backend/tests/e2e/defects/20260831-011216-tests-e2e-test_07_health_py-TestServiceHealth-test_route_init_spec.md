# E2E 缺陷报告：test_route_init_spec

- **测试 ID**: `tests/e2e/test_07_health.py::TestServiceHealth::test_route_init_spec`
- **发现时间**: 2026-08-31T01:12:16.682458
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
@contextlib.contextmanager
    def map_httpcore_exceptions() -> typing.Iterator[None]:
        global HTTPCORE_EXC_MAP
        if len(HTTPCORE_EXC_MAP) == 0:
            HTTPCORE_EXC_MAP = _load_httpcore_exceptions()
        try:
>           yield

.venv/lib/python3.11/site-packages/httpx/_transports/default.py:101: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
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
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

map = {<class 'TimeoutError'>: <class 'httpcore.ConnectTimeout'>, <class 'OSError'>: <class 'httpcore.ConnectError'>, <class 'anyio.BrokenResourceError'>: <class 'httpcore.ConnectError'>}

    @contextlib.contextmanager
    def map_exceptions(map: ExceptionMapping) -> typing.Iterator[None]:
        try:
            yield
        except Exception as exc:  # noqa: PIE786
            for from_exc, to_exc in map.items():
                if isinstance(exc, from_exc):
>                   raise to_exc(exc) from exc
E                   httpcore.ConnectError: All connection attempts failed

.venv/lib/python3.11/site-packages/httpcore/_exceptions.py:14: ConnectError

The above exception was the direct cause of the following exception:

self = <tests.e2e.test_07_health.TestServiceHealth object at 0x1038a1e50>
http_client = <httpx.AsyncClient object at 0x127fa8210>

    @pytest.mark.timeout(30)
    async def test_route_init_spec(self, http_client: httpx.AsyncClient) -> None:
        """路由初始化规格接口可访问（导航宏预设数据契约的源头）。"""
>       resp = await http_client.get("/api/v1/route/init")

tests/e2e/test_07_health.py:52: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
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
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    @contextlib.contextmanager
    def map_httpcore_exceptions() -> typing.Iterator[None]:
        global HTTPCORE_EXC_MAP
        if len(HTTPCORE_EXC_MAP) == 0:
            HTTPCORE_EXC_MAP = _load_httpcore_exceptions()
        try:
            yield
        except Exception as exc:
            mapped_exc = None
    
            for from_exc, to_exc in HTTPCORE_EXC_MAP.items():
                if not isinstance(exc, from_exc):
                    continue
                # We want to map to the most specific exception we can find.
                # Eg if `exc` is an `httpcore.ReadTimeout`, we want to map to
                # `httpx.ReadTimeout`, not just `httpx.TimeoutException`.
                if mapped_exc is None or issubclass(to_exc, mapped_exc):
                    mapped_exc = to_exc
    
            if mapped_exc is None:  # pragma: no cover
                raise
    
            message = str(exc)
>           raise mapped_exc(message) from exc
E           httpx.ConnectError: All connection attempts failed

.venv/lib/python3.11/site-packages/httpx/_transports/default.py:118: ConnectError
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
