"""阶段28：语音线上字节契约（前端视角）端到端测试。

对应 Rust 前端消费契约（frontend/src-tauri/src/voice/voice_session.rs）：
- 后端通过 voice WS `send_bytes` 发送**原始 f32le PCM 24kHz 单声道**裸字节
  （无信封、无 base64），由 voice_ws.py:529 `ws.send_bytes(s16le_to_f32le(chunk))` 产生。
- 前端按 4 字节一个 f32 样本解包，并以 24kHz 换算实时播放（voice_session.rs:319）。

触发方式（L0 层，不依赖 LLM/Agent）：
- 测试直接驱动 `VoiceTtsBridge.send_chat_tts_text`（voice_ws.py:468）——文本 →
  火山流式 TTS → s16le_to_f32le → send_audio_cb。生产链路 send_audio_cb =
  `ws.send_bytes`（裸字节管道，不做任何变换），前端 WS recv 拿到的就是桥出口的
  原始字节。测试进程内收集桥出口字节并解码断言，与前端收到的字节逐字节一致。
- 绕过 Agent 后不依赖 EvoCloud LLM 配额，只依赖火山 TTS（独立凭据），稳定可复现。

测试目标（前端角度，锁住此前只能靠人耳/实测才能发现的两个炸点）：
1. 字节格式 = f32le：帧长 4 的倍数、解码样本全为有限数、峰幅在合理范围。
2. 实时速率 ≈ 真实时间：后端节流预算 `_TTS_BUDGET_S=1.2s`（voice_ws.py:497），
   防止"合成比实时快 ~5x → Rust 2s ring buffer 溢出 → 后半句加速"回归。
3. 非空非静音：整段流峰值幅度超过阈值，证明真实 TTS 语音在发声。

采样率(24k)不可直接度量，但速率断言以 24000 为换算基准，两个方向都锁死：
- 若后端误发 48k f32：累计音频秒数翻倍 → 送达速率远超预算 → 被速率断言抓出；
- 若后端误发 16k f32：累计音频秒数减半 → 总耗时远超音频秒数 → 被下限断言抓出。
"""

from __future__ import annotations

import math
import struct
import time

import pytest

from tests.e2e.conftest import _config_value

pytestmark = pytest.mark.e2e

_TTS_SAMPLE_RATE_HZ = 24000
_TOTAL_SLACK_S = 2.5

_SENTENCES = [
    "Python 列表推导式是用单行表达式创建新列表的简洁语法。",
    "它比传统 for 循环更简洁易读，还可以通过条件进行筛选。",
    "它是 Python 中处理数据变换和过滤的推荐方式。",
]


async def _seed_volc_keys(system_config: list[dict]) -> bool:
    """从 API 配置取火山凭据，种入测试进程 DB（幂等），使 TTS 桥可读。"""
    from app.infrastructure.config.service import SystemConfigService
    from app.infrastructure.database.resource_manager import db_resource_manager

    app_id = _config_value(system_config, "SEEDUPLEX_APP_ID")
    access_key = _config_value(system_config, "SEEDUPLEX_ACCESS_KEY")
    if not app_id or not access_key:
        return False
    if not db_resource_manager.sync_engine:
        await db_resource_manager.initialize(create_tables=False, seed_data=False)
    SystemConfigService.set_value("SEEDUPLEX_APP_ID", app_id)
    SystemConfigService.set_value("SEEDUPLEX_ACCESS_KEY", access_key)
    return True


class _FrameCollector:
    """进程内收集桥出口音频字节（等价于生产 `ws.send_bytes` 裸管道）。"""

    def __init__(self) -> None:
        self.frames: list[tuple[float, bytes]] = []

    async def __call__(self, audio: bytes) -> None:
        self.frames.append((time.monotonic(), audio))


def _samples_from_frames(frames: list[tuple[float, bytes]]) -> list[float]:
    samples: list[float] = []
    for _, payload in frames:
        assert len(payload) % 4 == 0, (
            f"音频帧字节数应为 4 的倍数（f32le），实际 {len(payload)} 字节"
        )
        samples.extend(struct.unpack(f"<{len(payload) // 4}f", payload))
    return samples


class TestVoiceWireFormat:
    """E2E-SC-028: 线上字节契约从前端角度验证格式/速率/能量。"""

    @pytest.mark.timeout(180)
    @pytest.mark.real
    async def test_wire_f32le_24k_and_realtime_pacing(
        self,
        system_config: list[dict],
    ) -> None:
        """直接驱动 TTS 桥（L0 层，无 LLM），按前端契约解码断言。"""
        if not await _seed_volc_keys(system_config):
            pytest.skip("火山引擎未配置，跳过真实 TTS 线上字节契约测试")

        from app.api.routes.voice_ws import VoiceTtsBridge

        collector = _FrameCollector()
        bridge = VoiceTtsBridge("e2e-wire-thread", "e2e-wire-bridge", collector)
        try:
            await bridge.connect()
            for i, sentence in enumerate(_SENTENCES):
                await bridge.send_chat_tts_text(
                    start=(i == 0), end=(i == len(_SENTENCES) - 1), content=sentence
                )
        finally:
            await bridge.close()

        # send_chat_tts_text 逐句 await 完整流（含节流），返回时全部帧已产出
        frames = collector.frames
        assert frames, "TTS 桥应产生音频帧（f32le PCM 裸字节）"

        samples = _samples_from_frames(frames)

        # 1) f32le 格式：全为有限数，峰幅合理（TTS 归一化后 |x|<1，留 1.5 裕量）
        finite = all(math.isfinite(s) for s in samples)
        assert finite, "存在非有限数样本（inf/nan），不是合法 f32le PCM"
        peak = max(abs(s) for s in samples)
        assert peak <= 1.5, f"峰幅异常: {peak:.3f}，超出 f32 归一化范围"
        assert peak > 0.05, f"整段静音或能量过低: peak={peak:.4f}"

        # 2) 采样率+实时速率（以 24000 为换算基准，两个方向都锁死）
        audio_seconds = len(samples) / _TTS_SAMPLE_RATE_HZ
        t_first = frames[0][0]
        t_last = frames[-1][0]
        wall_seconds = t_last - t_first

        # 音频必须足够长，速率断言才有意义（短音频会被首帧突发抬高失真）
        assert audio_seconds >= 3.0, (
            f"合成音频过短无法评估实时速率: {audio_seconds:.2f}s"
        )

        # 送达速率 = 音频秒数 / 送达墙钟秒数。节流生效时整体 ≈1.1~1.6x
        # （首帧合成延迟 + 1.2s 预算突发抬升）；若节流失效，Volc 合成比实时快
        # ~5x，速率会冲到 4x+，直接抓出 "Rust ring buffer 溢出 → 后半句加速"。
        # 不用绝对 ahead：后端 t0 到首帧的合成延迟会恒定污染 ahead 值（实测
        # 预算 1.2s 却显示 4.0s），速率对合成延迟免疫。
        rate = audio_seconds / wall_seconds
        assert rate <= 1.8, (
            f"音频送达速率 {rate:.2f}x 过快（应 ≤1.8x），后端节流失效，"
            f"播放将快于实时导致 Rust ring buffer 溢出"
        )

        # 下限：整段送达不应显著慢于音频时长（防采样率/速率误判导致欠载）
        assert wall_seconds <= audio_seconds + _TOTAL_SLACK_S, (
            f"音频 {audio_seconds:.2f}s 耗时 {wall_seconds:.2f}s 送达，"
            f"超出 {_TOTAL_SLACK_S}s 裕量（播放将欠载/卡顿）"
        )
