# E2E 缺陷报告：test_double_stop_terminates_run_once

- **测试 ID**: `tests/e2e/test_06_control.py::TestStopEdgeCases::test_double_stop_terminates_run_once`
- **发现时间**: 2026-08-31T01:12:16.372303
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
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

map = {<class 'h11._util.RemoteProtocolError'>: <class 'httpcore.RemoteProtocolError'>}

    @contextlib.contextmanager
    def map_exceptions(map: ExceptionMapping) -> typing.Iterator[None]:
        try:
            yield
        except Exception as exc:  # noqa: PIE786
            for from_exc, to_exc in map.items():
                if isinstance(exc, from_exc):
>                   raise to_exc(exc) from exc
E                   httpcore.RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)

.venv/lib/python3.11/site-packages/httpcore/_exceptions.py:14: RemoteProtocolError

The above exception was the direct cause of the following exception:

self = <tests.e2e.test_06_control.TestStopEdgeCases object at 0x1038b10d0>
http_client = <httpx.AsyncClient object at 0x1275e5a50>
thread_id = 'e2e-e3bbfa1352674fe1'

    @pytest.mark.timeout(180)
    async def test_double_stop_terminates_run_once(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """连续两次 stop 后，Agent 仅被取消一次并到达终态。"""
        await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "帮我深度调研这个项目"},
        )
        await asyncio.sleep(0.3)
    
        resp1 = await http_client.post(
            "/api/v1/chat/stop", json={"thread_id": thread_id, "message": "stop"}
        )
        assert resp1.status_code == 200, resp1.text
        assert resp1.json()["status"] == "stopping"
    
        resp2 = await http_client.post(
            "/api/v1/chat/stop", json={"thread_id": thread_id, "message": "stop"}
        )
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["status"] == "stopping"
    
>       result = await observe_agent_run(
            http_client, thread_id, timeout=150.0, expect_start=False
        )

tests/e2e/test_06_control.py:231: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
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
E           httpx.RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)

.venv/lib/python3.11/site-packages/httpx/_transports/default.py:118: RemoteProtocolError
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_06_control.py::TestStopEdgeCases::test_double_stop_terminates_run_once -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
