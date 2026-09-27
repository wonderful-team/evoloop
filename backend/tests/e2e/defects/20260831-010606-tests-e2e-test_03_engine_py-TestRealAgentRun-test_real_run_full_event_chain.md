# E2E 缺陷报告：test_real_run_full_event_chain

- **测试 ID**: `tests/e2e/test_03_engine.py::TestRealAgentRun::test_real_run_full_event_chain`
- **发现时间**: 2026-08-31T01:06:06.777851
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_03_engine.TestRealAgentRun object at 0x1038f4ad0>
http_client = <httpx.AsyncClient object at 0x158bdbd50>
thread_id = 'e2e-7f840b2de6b349fb', unique_marker = 'e2e-real-19fcd5f0'

    @pytest.mark.timeout(240)
    async def test_real_run_full_event_chain(
        self, http_client: httpx.AsyncClient, thread_id: str, unique_marker: str
    ) -> None:
        """真实运行完整事件链：run_start → token/message/progress → run_end(done)。
    
        工具型提示词保证触发 on_tool_start，从而真实链路必须发出 progress 事件；
        token 由 LLM 流式回调（TransparentCallbackHandler）批量发布，message 为消息块同步事件。
        """
        event_names: list[str] = []
    
        async def _on_event(ev: object) -> None:
            event_names.append(getattr(ev, "event", ""))
    
        observer_task = asyncio.create_task(
            collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event == "run_end",
                timeout=200.0,
                on_event=_on_event,
                desc="真实完整事件链 run_end",
            )
        )
        await asyncio.sleep(0)  # 预订阅：确保 run_start 之前建立 SSE 连接
    
        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": (
                    f"请使用 execute_command 工具运行命令 `echo chain-{unique_marker}`，"
                    "并返回命令输出。"
                ),
                "project_id": 0,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"
    
        events = await observer_task
        run_end = next(ev for ev in events if ev.event == "run_end").json
        status = run_end.get("status")
        if status == "quota_exhausted":
            verify_quota_exhausted_feedback(events)
            return
    
        if status in ("failed", "quota_exhausted", "cancelled"):
>           pytest.fail(
                f"真实运行未正常完成，status={status}, run_end={run_end}, "
                f"event_names={event_names}"
            )
E           Failed: 真实运行未正常完成，status=failed, run_end={'type': 'run_end', 'thread_id': 'e2e-7f840b2de6b349fb', 'run_id': 'run-237e158d', 'status': 'failed', 'final_outcome': 'failed'}, event_names=['activity', 'message', 'run_start', 'run_end']

tests/e2e/test_03_engine.py:122: Failed
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_03_engine.py::TestRealAgentRun::test_real_run_full_event_chain -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
