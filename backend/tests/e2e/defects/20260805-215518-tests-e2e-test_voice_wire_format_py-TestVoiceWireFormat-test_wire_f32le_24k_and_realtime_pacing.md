# E2E 缺陷报告：test_wire_f32le_24k_and_realtime_pacing

- **测试 ID**: `tests/e2e/test_voice_wire_format.py::TestVoiceWireFormat::test_wire_f32le_24k_and_realtime_pacing`
- **发现时间**: 2026-08-05T21:55:18.134351
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_voice_wire_format.TestVoiceWireFormat object at 0x1051d1c90>
voice_conn = <tests.e2e.conftest.VoiceConn object at 0x1054be5d0>
volc_configured = True

    @pytest.mark.timeout(180)
    @pytest.mark.real
    async def test_wire_f32le_24k_and_realtime_pacing(
        self,
        voice_conn: VoiceConn,
        volc_configured: bool,
    ) -> None:
        """dialogue 路由触发 Agent 流式 TTS，按前端契约解码断言。"""
        if not volc_configured:
            pytest.skip("火山引擎未配置，跳过真实 TTS 线上字节契约测试")
    
        await voice_conn.send_route(
            "用两句话介绍 Python 的列表推导，每句话以句号结尾。"
        )
    
        final = await voice_conn.wait_terminal_route_result(timeout=90.0)
        final_status = final["body"]["status"]
        assert final_status == "done", f"终态异常: {final}"
    
        await asyncio.sleep(1.0)
        frames = voice_conn.audio_frames
>       assert frames, "dialogue 路由应产生 TTS 音频帧（f32le PCM 裸字节）"
E       AssertionError: dialogue 路由应产生 TTS 音频帧（f32le PCM 裸字节）
E       assert []

tests/e2e/test_voice_wire_format.py:71: AssertionError
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_voice_wire_format.py::TestVoiceWireFormat::test_wire_f32le_24k_and_realtime_pacing -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
