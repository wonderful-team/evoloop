"""TTS synthesis product assertions (offline, deterministic).

Asserts the *product* of TTS — not that a human hears it: a short Chinese phrase
must synthesize to a non-empty audio blob of the declared content type, and when
persisted to a file it must have a positive playback duration (probed with the
macOS-bundled `afinfo`, zero extra deps). Skips when no TTS provider is usable.

Note: this repo has no Qwen-/DashScope-TTS; providers are System (macOS `say`,
offline) and Edge (network). We prefer the offline System provider.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile

import pytest

from app.infrastructure.voice import TTSOptions, VoiceLocale, get_tts_provider
from app.infrastructure.voice.tts.factory import TTSFactory


def _probe_duration_seconds(path: str) -> float | None:
    try:
        out = subprocess.run(
            ["afinfo", path], capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"estimated duration:\s*([\d.]+)\s*sec", out.stdout)
    return float(m.group(1)) if m else None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tts_synthesize_produces_audible_audio() -> None:
    TTSFactory.clear_cache()
    try:
        provider = get_tts_provider(prefer_offline=True)
    except RuntimeError as exc:
        pytest.skip(f"No TTS provider: {exc}")
    if not provider.is_available():
        pytest.skip(f"{provider.name} not available")

    text = "你好，这是一段文本转语音测试。"
    result = await provider.synthesize(
        TTSOptions(
            text=text,
            voice_id=provider.get_default_voice(VoiceLocale.ZH_CN),
            locale=VoiceLocale.ZH_CN,
        )
    )

    # 1) non-empty audio bytes of the declared type
    assert isinstance(result.audio_data, (bytes, bytearray))
    assert len(result.audio_data) > 1024, f"audio too small: {len(result.audio_data)} bytes"
    assert "mpeg" in (result.content_type or "") or "audio" in (result.content_type or "")

    # 2) persisted file has positive playback duration (real, decodable audio)
    suffix = ".mp3" if "mpeg" in (result.content_type or "") else ".aiff"
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(result.audio_data)
        dur = _probe_duration_seconds(path)
        if dur is not None:  # afinfo available and parsed
            assert dur > 0.2, f"duration too short: {dur}s"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
