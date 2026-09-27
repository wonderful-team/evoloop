# E2E 缺陷报告：test_wire_f32le_24k_and_realtime_pacing

- **测试 ID**: `tests/e2e/test_voice_wire_format.py::TestVoiceWireFormat::test_wire_f32le_24k_and_realtime_pacing`
- **发现时间**: 2026-08-06T01:03:29.790690
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_voice_wire_format.TestVoiceWireFormat object at 0x1054102d0>
voice_conn = <tests.e2e.conftest.VoiceConn object at 0x105504e90>
system_config = [{'description': 'Device identifier for EvoLoop Link', 'key': 'EVOCLOUD_DEVICE_NAME', 'value': 'Mac-mini.local'}, {'de...NT_WEBSITE', 'value': 'https://evoloop.cn'}, {'description': None, 'key': 'LLM_CONFIG_TYPE', 'value': 'platform'}, ...]

    @pytest.mark.timeout(180)
    @pytest.mark.real
    async def test_wire_f32le_24k_and_realtime_pacing(
        self,
        voice_conn: VoiceConn,
        system_config: list[dict],
    ) -> None:
        """直接驱动 TTS 桥（L0 层，无 LLM），按前端契约解码断言。"""
        if not await _seed_volc_keys(system_config):
            pytest.skip("火山引擎未配置，跳过真实 TTS 线上字节契约测试")
    
        from app.api.routes.voice_ws import VoiceTtsBridge
    
        bridge = VoiceTtsBridge(
            voice_conn.thread_id, "e2e-wire-bridge", voice_conn.ws.send
        )
        try:
            await bridge.connect()
            for i, sentence in enumerate(_SENTENCES):
                await bridge.send_chat_tts_text(
                    start=(i == 0), end=(i == len(_SENTENCES) - 1), content=sentence
                )
        finally:
            await bridge.close()
    
        # 等流收尾：连续 _STREAM_IDLE_S 秒无新帧视为句末收尾
        while True:
            n = len(voice_conn.audio_frames)
            await asyncio.sleep(_STREAM_IDLE_S)
            if len(voice_conn.audio_frames) == n:
                break
    
        frames = voice_conn.audio_frames
>       assert frames, "TTS 桥应产生音频帧（f32le PCM 裸字节）"
E       AssertionError: TTS 桥应产生音频帧（f32le PCM 裸字节）
E       assert []

tests/e2e/test_voice_wire_format.py:110: AssertionError
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
