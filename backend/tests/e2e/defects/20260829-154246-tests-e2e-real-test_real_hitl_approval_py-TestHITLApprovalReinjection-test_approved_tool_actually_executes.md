# E2E 缺陷报告：test_approved_tool_actually_executes

- **测试 ID**: `tests/e2e/real/test_real_hitl_approval.py::TestHITLApprovalReinjection::test_approved_tool_actually_executes`
- **发现时间**: 2026-08-29T15:42:46.412182
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <test_real_hitl_approval.TestHITLApprovalReinjection object at 0x110511d10>
http_client = <httpx.AsyncClient object at 0x1109132d0>
thread_id = 'e2e-afeaa3b1c3824414'
temp_project = {'imported': True, 'path': PosixPath('/Users/huangjinhuan/Projects/e2e-real-0c935152'), 'project_id': 198}

    @pytest.mark.timeout(240)
    async def test_approved_tool_actually_executes(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        temp_project: dict[str, Any],
    ) -> None:
        project_id = temp_project.get("project_id")
        if not project_id or not temp_project.get("imported"):
            pytest.skip("临时项目导入失败，无法测试项目级 HITL 授权")
    
        marker = f"e2e-hitl-{uuid.uuid4().hex[:8]}"
        target = f"/tmp/{marker}.txt"  # 项目工作区之外 → 触发授权 HITL
    
        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": (
                    f"请用 write_file 工具把内容 `{marker}` 写入文件 `{target}`，"
                    "如果需要确认请确认后执行。"
                ),
                "project_id": project_id,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] in ("queued", "done")
    
        state = ApprovalState()
        on_event = await _make_approve_handler(http_client, thread_id, state)
        try:
>           events = await collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event == "run_end",
                timeout=200.0,
                desc="HITL 审批后 run_end",
                on_event=on_event,
            )

tests/e2e/real/test_real_hitl_approval.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <httpx.AsyncClient object at 0x1109132d0>
url = '/api/v1/stream/chat/e2e-afeaa3b1c3824414'
pred = <function TestHITLApprovalReinjection.test_approved_tool_actually_executes.<locals>.<lambda> at 0x110959120>

    async def collect_sse_until(
        client: httpx.AsyncClient,
        url: str,
        pred: Callable[[SSEEmitter], bool],
        *,
        timeout: float = 90.0,
        desc: str = "目标 SSE 事件",
        on_event: Callable[[SSEEmitter], Awaitable[None]] | None = None,
    ) -> list[SSEEmitter]:
        """收集 SSE 事件直到谓词满足，返回全部已收到事件（含触发事件）。
    
        可选的 ``on_event`` 在每次收到事件后被异步调用，可用于在收集过程中
        触发副作用（例如自动取消 HITL 请求）。"""
        received: list[SSEEmitter] = []
        result: list[SSEEmitter] | None = None
    
        async def _handler(ev: SSEEmitter) -> Any:
            received.append(ev)
            if on_event is not None:
                await on_event(ev)
            if pred(ev):
                nonlocal result
                result = list(received)
                return _SSE_STOP
            return None
    
>       await _read_sse_stream(client, url, _handler, timeout=timeout)

tests/e2e/conftest.py:186: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <httpx.AsyncClient object at 0x1109132d0>
url = '/api/v1/stream/chat/e2e-afeaa3b1c3824414'
handler = <function collect_sse_until.<locals>._handler at 0x1109591c0>

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
E                       TimeoutError: SSE 读取超时(200.0s)

tests/e2e/conftest.py:128: TimeoutError

During handling of the above exception, another exception occurred:

self = <test_real_hitl_approval.TestHITLApprovalReinjection object at 0x110511d10>
http_client = <httpx.AsyncClient object at 0x1109132d0>
thread_id = 'e2e-afeaa3b1c3824414'
temp_project = {'imported': True, 'path': PosixPath('/Users/huangjinhuan/Projects/e2e-real-0c935152'), 'project_id': 198}

    @pytest.mark.timeout(240)
    async def test_approved_tool_actually_executes(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        temp_project: dict[str, Any],
    ) -> None:
        project_id = temp_project.get("project_id")
        if not project_id or not temp_project.get("imported"):
            pytest.skip("临时项目导入失败，无法测试项目级 HITL 授权")
    
        marker = f"e2e-hitl-{uuid.uuid4().hex[:8]}"
        target = f"/tmp/{marker}.txt"  # 项目工作区之外 → 触发授权 HITL
    
        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": (
                    f"请用 write_file 工具把内容 `{marker}` 写入文件 `{target}`，"
                    "如果需要确认请确认后执行。"
                ),
                "project_id": project_id,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] in ("queued", "done")
    
        state = ApprovalState()
        on_event = await _make_approve_handler(http_client, thread_id, state)
        try:
            events = await collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event == "run_end",
                timeout=200.0,
                desc="HITL 审批后 run_end",
                on_event=on_event,
            )
        except TimeoutError as exc:
>           pytest.fail(f"审批后未在窗口内收到 run_end: {exc}")
E           Failed: 审批后未在窗口内收到 run_end: SSE 读取超时(200.0s)

tests/e2e/real/test_real_hitl_approval.py:139: Failed
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/real/test_real_hitl_approval.py::TestHITLApprovalReinjection::test_approved_tool_actually_executes -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
