# E2E 缺陷报告：test_supervisor_comfort_routed_envelope

- **测试 ID**: `tests/e2e/test_18_voice_reply_points.py::TestVoiceReplyPoints::test_supervisor_comfort_routed_envelope`
- **发现时间**: 2026-08-29T15:11:42.586479
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_18_voice_reply_points.TestVoiceReplyPoints object at 0x10350db10>
voice_conn = <tests.e2e.conftest.VoiceConn object at 0x10411da90>

    @pytest.mark.timeout(200)
    async def test_supervisor_comfort_routed_envelope(
        self, voice_conn: VoiceConn
    ) -> None:
        """回复点5：Supervisor 派活时推送 routed 安抚信封，summary 为安抚文本。
    
        复杂任务经 L0 未命中转投 Agent 后，Supervisor 首次派活给 Worker 的
        ai+tool_calls MessageBlock 会被 VoiceChannel.send 去重并 fire-and-forget
        推送 ``voice.route_result {status:"routed", summary}``。
        注意：现有套件的 ``wait_terminal_route_result`` 会忽略该非终态信封，
        本用例改用 ``_collect_until_terminal`` 显式收集。
        """
        await voice_conn.send_route("请使用 execute_command 工具执行 echo 命令")
    
        routed, terminal = await _collect_until_terminal(
            voice_conn, _ROUTE_DRAIN_TIMEOUT
        )
>       assert terminal is not None, (
            f"150s 内未收到任何 voice.route_result 终态，thread={voice_conn.thread_id}"
        )
E       AssertionError: 150s 内未收到任何 voice.route_result 终态，thread=e2e-4c87f9e3a6994295
E       assert None is not None

tests/e2e/test_18_voice_reply_points.py:135: AssertionError
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_18_voice_reply_points.py::TestVoiceReplyPoints::test_supervisor_comfort_routed_envelope -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
