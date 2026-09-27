# E2E 缺陷报告：test_wire_f32le_24k_and_realtime_pacing

- **测试 ID**: `tests/e2e/test_voice_wire_format.py::TestVoiceWireFormat::test_wire_f32le_24k_and_realtime_pacing`
- **发现时间**: 2026-08-05T23:25:04.434290
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_voice_wire_format.TestVoiceWireFormat object at 0x1038c7850>
voice_conn = <tests.e2e.conftest.VoiceConn object at 0x106304c10>

    @pytest.mark.timeout(240)
    @pytest.mark.real
    async def test_wire_f32le_24k_and_realtime_pacing(
        self,
        voice_conn: VoiceConn,
    ) -> None:
        """dialogue 模式经 voice.start 注册 TTS 桥后路由触发 Agent 流式 TTS。"""
        # 1) voice.start 注册 TTS 桥（voice_ws.py:1320），否则只有事件无音频字节
        await voice_conn.send_type(
            "voice.start", {"thread_id": voice_conn.thread_id, "mode": "dialogue"}
        )
    
        # 2) 路由触发 Agent 回复 → 桥逐句合成 → send_bytes 音频帧。
        #    不等 route_result（LLM 慢时可能 90s+ 才终态），前端真正关心的是
        #    音频流本身，直接等首帧到达。
        await voice_conn.send_route(_PROMPT)
    
        deadline = time.monotonic() + _FIRST_FRAME_TIMEOUT_S
        while time.monotonic() < deadline and not voice_conn.audio_frames:
            await asyncio.sleep(0.2)
>       assert voice_conn.audio_frames, (
            f"{_FIRST_FRAME_TIMEOUT_S:.0f}s 内未收到任何 TTS 音频帧"
        )
E       AssertionError: 90s 内未收到任何 TTS 音频帧
E       assert []
E        +  where [] = <tests.e2e.conftest.VoiceConn object at 0x106304c10>.audio_frames

tests/e2e/test_voice_wire_format.py:79: AssertionError
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
