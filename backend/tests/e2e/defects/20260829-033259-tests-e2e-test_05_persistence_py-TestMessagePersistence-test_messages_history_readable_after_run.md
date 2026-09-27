# E2E 缺陷报告：test_messages_history_readable_after_run

- **测试 ID**: `tests/e2e/test_05_persistence.py::TestMessagePersistence::test_messages_history_readable_after_run`
- **发现时间**: 2026-08-29T03:32:59.987157
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_05_persistence.TestMessagePersistence object at 0x31e39ec10>
http_client = <httpx.AsyncClient object at 0x31e617c90>
thread_id = 'e2e-c339cefb573c423d'

    @pytest.mark.timeout(180)
    async def test_messages_history_readable_after_run(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """真实 LLM 运行跑完后，消息历史读取路径（归一化）保持可用且包含 AI 回复。"""
        text = "你好，请确认消息历史读取链路正常。"
        observer_task = asyncio.create_task(
            observe_agent_run(
                http_client, thread_id, timeout=150.0, expect_start=False
            )
        )
        await asyncio.sleep(0)  # 预订阅 SSE，避免 run_start 丢弃
    
        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": text}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"
    
>       result = await observer_task

tests/e2e/test_05_persistence.py:69: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <httpx.AsyncClient object at 0x31e617c90>, tid = 'e2e-c339cefb573c423d'

    async def observe_agent_run(
        client: httpx.AsyncClient,
        tid: str,
        *,
        timeout: float = 120.0,
        expect_start: bool = True,
    ) -> AgentLoopResult:
        """订阅 SSE 直到 run_end（或 timeout），汇总事件链。"""
        run_start: SSEEmitter | None = None
        run_end: SSEEmitter | None = None
        message_blocks: list[SSEEmitter] = []
        all_events: list[SSEEmitter] = []
    
        async def _handler(ev: SSEEmitter) -> Any:
            nonlocal run_start, run_end
            all_events.append(ev)
            if ev.event == "run_start":
                run_start = ev
            elif ev.event == "run_end":
                run_end = ev
                return _SSE_STOP
            elif ev.event == "message":
                message_blocks.append(ev)
            return None
    
>       await _read_sse_stream(
            client, f"/api/v1/stream/chat/{tid}", _handler, timeout=timeout
        )

tests/e2e/conftest.py:540: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <httpx.AsyncClient object at 0x31e617c90>
url = '/api/v1/stream/chat/e2e-c339cefb573c423d'
handler = <function observe_agent_run.<locals>._handler at 0x31e60dda0>

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
2. 运行测试: `uv run pytest tests/e2e/test_05_persistence.py::TestMessagePersistence::test_messages_history_readable_after_run -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
