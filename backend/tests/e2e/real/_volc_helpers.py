"""真实火山引擎语音测试的共享工具（不采集为测试用例）。

自包含闭环：系统 VolcTtsClient 合成 → ffmpeg 解码 16k 单声道 PCM →
系统 VolcAsrClient 识别 → 断言还原。密钥从后端系统配置读取，不硬编码。
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from app.infrastructure.voice.volc_asr import VolcAsrClient
from app.infrastructure.voice.volc_tts import VolcTtsClient
from tests.e2e.conftest import _config_value

TTS_TEXT = "现在几点了"


def volc_keys(system_config: list[dict]) -> tuple[str, str]:
    """从系统配置取火山 AppID/AccessKey；缺失时 raise SkipTest。"""
    app_id = _config_value(system_config, "SEEDUPLEX_APP_ID")
    access_key = _config_value(system_config, "SEEDUPLEX_ACCESS_KEY")
    if not app_id or not access_key:
        pytest.skip("火山引擎未配置（SEEDUPLEX_APP_ID/ACCESS_KEY 缺失），跳过真实语音测试")
    return app_id, access_key


def require_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("缺少 ffmpeg/ffprobe，无法将 TTS mp3 解码为 PCM，跳过回环用例")


async def tts_synthesize(app_id: str, access_key: str, text: str) -> tuple[bytes, float]:
    """复刻系统 generate_volc_tts 的完整调用序列，用系统 VolcTtsClient。"""
    client = VolcTtsClient(app_id, access_key, session_id="real-test")
    t0 = time.monotonic()
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
        await client.start_session(VolcTtsClient.DEFAULT_SPEAKER)
        await client.send_text(text)
        await client.finish_session()
        audio = await asyncio.wait_for(client.receive_audio(timeout=30.0), timeout=40)
    finally:
        await client.close()
    return audio, time.monotonic() - t0


async def asr_recognize_pcm(app_id: str, access_key: str, pcm_path: Path) -> tuple[str, float]:
    """用系统 VolcAsrClient 识别 16k 单声道 PCM，返回 (最终文本, 处理耗时)。

    与系统 _finalize_asr_session 相同的消费方式：分块送音频 → 负包 → 收集到 459。
    """
    client = VolcAsrClient(app_id, access_key)
    t0 = time.monotonic()
    try:
        await client.connect()
        with open(pcm_path, "rb") as f:
            while True:
                chunk = f.read(3200)  # 200ms @16k
                if not chunk:
                    break
                await client.send_audio(chunk)
        await client.finish()
        text = ""
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            resp = await asyncio.wait_for(client.receive_response(), timeout=5)
            origin = ((resp.get("payload_msg") or {}).get("extra") or {}).get("origin_text") or ""
            if origin:
                text = origin
            if resp.get("event") == 459:
                break
    finally:
        await client.close()
    return text.strip(), time.monotonic() - t0


def mp3_duration(mp3: bytes, path: Path) -> float:
    path.write_bytes(mp3)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise AssertionError(f"ffprobe 无法解码 mp3: {out.stderr.strip()}")
    return float(out.stdout.strip())


def mp3_to_pcm16k(mp3: bytes, mp3_path: Path, pcm_path: Path) -> None:
    mp3_path.write_bytes(mp3)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(mp3_path),
         "-ac", "1", "-ar", "16000", "-f", "s16le", str(pcm_path)],
        check=True,
        capture_output=True,
    )
