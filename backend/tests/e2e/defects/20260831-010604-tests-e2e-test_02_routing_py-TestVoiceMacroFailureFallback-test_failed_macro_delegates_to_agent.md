# E2E 缺陷报告：test_failed_macro_delegates_to_agent

- **测试 ID**: `tests/e2e/test_02_routing.py::TestVoiceMacroFailureFallback::test_failed_macro_delegates_to_agent`
- **发现时间**: 2026-08-31T01:06:04.800710
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_02_routing.TestVoiceMacroFailureFallback object at 0x1038590d0>
http_client = <httpx.AsyncClient object at 0x158ba3410>
thread_id = 'e2e-7d9163121e944096'
voice_conn = <tests.e2e.conftest.VoiceConn object at 0x158b5c810>

    @pytest.mark.real
    @pytest.mark.slow
    @pytest.mark.timeout(300)
    async def test_failed_macro_delegates_to_agent(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        voice_conn: Any,
    ) -> None:
        """exit 1 的 bash 宏在 voice 源必然失败 → 转投 Agent → 终态带 AI summary。
    
        本地宏执行失败会立即推送固定话术 {status: failed, summary: "执行失败"}；
        转投 Agent 后需要较长时间由 LLM 处理并返回自由文本 summary。
        以"短窗口内无固定话术终态 + 长等待后出现 AI summary"判定转投成功。
        """
        # ``改名`` 是 BERT 已学习的标签且不是现有 DB 宏名称，``帮我你以后叫小明``
        # 为其训练示例，宏脚本为必然失败的 bash exit 1，用于验证 voice 源失败后的 Agent 回退。
        name = "改名"
        trigger = "帮我你以后叫小明"
        macro_id = await _create_failing_macro(http_client, name, trigger)
        try:
            await voice_conn.send_route(trigger)
    
            # 短窗口：本地宏（成功或失败）应在数秒内返回固定话术终态。
            try:
                env = await voice_conn.wait_terminal_route_result(timeout=12.0)
            except TimeoutError:
                env = None
    
            if env is None:
                # 无快速本地终态 → 宏失败已转投 Agent，等待 Agent 侧终态。
>               env = await voice_conn.wait_terminal_route_result(timeout=180.0)

tests/e2e/test_02_routing.py:649: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <tests.e2e.conftest.VoiceConn object at 0x158b5c810>, timeout = 180.0

    async def wait_terminal_route_result(self, timeout: float = 90.0) -> dict[str, Any]:
        """等待一个终态 voice.route_result（忽略 supervisor 的 routed 安抚信封）。"""
        env = await self._drain_until(
            lambda e: (
                e.get("type") == "voice.route_result"
                and e.get("body", {}).get("status") in {"done", "failed", "cancelled"}
            ),
            timeout=timeout,
        )
        if env is None:
>           raise TimeoutError(
                f"未收到终态 voice.route_result({timeout}s)，thread={self.thread_id}"
            )
E           TimeoutError: 未收到终态 voice.route_result(180.0s)，thread=e2e-7d9163121e944096

tests/e2e/conftest.py:449: TimeoutError
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_02_routing.py::TestVoiceMacroFailureFallback::test_failed_macro_delegates_to_agent -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
