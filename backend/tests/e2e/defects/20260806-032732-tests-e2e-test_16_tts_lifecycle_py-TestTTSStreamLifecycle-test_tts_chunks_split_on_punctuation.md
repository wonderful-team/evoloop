# E2E 缺陷报告：test_tts_chunks_split_on_punctuation

- **测试 ID**: `tests/e2e/test_16_tts_lifecycle.py::TestTTSStreamLifecycle::test_tts_chunks_split_on_punctuation`
- **发现时间**: 2026-08-06T03:27:32.127370
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_16_tts_lifecycle.TestTTSStreamLifecycle object at 0x105afb190>
voice_conn = <tests.e2e.conftest.VoiceConn object at 0x109eabb90>
volc_configured = True, thread_id = 'e2e-79ac28c52dcd4118'

    @pytest.mark.timeout(120)
    @pytest.mark.real
    async def test_tts_chunks_split_on_punctuation(
        self,
        voice_conn: VoiceConn,
        volc_configured: bool,
        thread_id: str,
    ) -> None:
        """多句回复走 Agent 流式 TTS，验证边界与最终 done 信封行为。"""
        if not volc_configured:
            pytest.skip("火山引擎未配置，跳过真实 TTS 生命周期测试")
    
        prompt = "用三句话介绍 Python 的列表推导，每句话以句号结尾。"
    
        await voice_conn.send_route(prompt)
    
        final = await voice_conn.wait_terminal_route_result(timeout=90.0)
        final_status = final["body"]["status"]
        assert final_status in (
            "done",
            "failed",
        ), f"终态异常: {final_status}"
    
        # 给收集器一点时间收尾
        await asyncio.sleep(1.0)
    
        voice_events = voice_conn.collected_events
    
        tts_boundaries = [
            e for e in voice_events if e.get("type") == "voice.tts_boundary"
        ]
    
        # 每个 tts_boundary 句子应以句末标点结尾
        # （最后一条 boundary 可能是会话结束时的剩余片段，允许未完成句）
        punctuation = "。！？.!?\n…"
        for i, boundary in enumerate(tts_boundaries):
            sentence = boundary.get("body", {}).get("sentence", "")
            if sentence:
                if i == len(tts_boundaries) - 1:
                    continue
                assert (
                    sentence[-1] in punctuation
                ), f"tts_boundary 句子未以标点结尾: {sentence!r}"
    
        # 应有至少一条 voice.token 流式事件（后端已接线推送实时播报文本）
        tokens = [
            e for e in voice_events if e.get("type") == "voice.token"
        ]
>       assert tokens, "流式播放时应推送 voice.token 事件（后端已接线）"
E       AssertionError: 流式播放时应推送 voice.token 事件（后端已接线）
E       assert []

tests/e2e/test_16_tts_lifecycle.py:71: AssertionError
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_16_tts_lifecycle.py::TestTTSStreamLifecycle::test_tts_chunks_split_on_punctuation -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
