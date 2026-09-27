# E2E 缺陷报告：test_stop_soft_interrupt_terminates_run

- **测试 ID**: `tests/e2e/test_06_control.py::TestStopCommand::test_stop_soft_interrupt_terminates_run`
- **发现时间**: 2026-08-31T01:09:24.605021
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_06_control.TestStopCommand object at 0x1038eb910>
http_client = <httpx.AsyncClient object at 0x12757b6d0>
thread_id = 'e2e-47a13762b73e4602'

    @pytest.mark.timeout(180)
    async def test_stop_soft_interrupt_terminates_run(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """stop 软信号 → 引擎节点循环软截断 → run_end（cancelled 为期望终态）。"""
        await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "帮我深度调研一下这个项目"},
        )
        await asyncio.sleep(0.5)
        await http_client.post(
            "/api/v1/chat/stop",
            json={"thread_id": thread_id, "message": "stop"},
        )
    
>       result = await observe_agent_run(
            http_client, thread_id, timeout=150.0, expect_start=False
        )

tests/e2e/test_06_control.py:61: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
tests/e2e/conftest.py:540: in observe_agent_run
    await _read_sse_stream(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <httpx.AsyncClient object at 0x12757b6d0>
url = '/api/v1/stream/chat/e2e-47a13762b73e4602'
handler = <function observe_agent_run.<locals>._handler at 0x127576660>

    async def _read_sse_stream(
        client: httpx.AsyncClient,
        url: str,
        handler: Callable[[SSEEmitter], Awaitable[Any]],
        *,
        timeout: float = 90.0,
    ) -> None:
        """流式读取 SSE 端点并同步调用 handler；handler 返回 _SSE_STOP 时立即结束。"""
        deadline = time.monotonic() + timeout
        async with client.stream(
            "GET", url, timeout=httpx.Timeout(timeout, read=timeout)
        ) as resp:
            resp.raise_for_status()
            event_name = ""
            data_lines: list[str] = []
            line_iter = resp.aiter_lines()
            try:
                while True:
                    try:
                        line = await anext(line_iter)
                    except StopAsyncIteration:
                        break
                    if time.monotonic() > deadline:
>                       raise TimeoutError(f"SSE 读取超时({timeout}s)")
E                       TimeoutError: SSE 读取超时(150.0s)

tests/e2e/conftest.py:128: TimeoutError
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_06_control.py::TestStopCommand::test_stop_soft_interrupt_terminates_run -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
