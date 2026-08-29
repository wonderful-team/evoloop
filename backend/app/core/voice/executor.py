"""Voice executor — task cancellation, active Volcengine client registry, and
legacy voice WS push helpers.

The actual WebSocket transport now lives in ``VoiceChannel``
(``app.core.channel.output.voice_channel``).  The helpers below are thin
backward-compatible wrappers that delegate to ``VoiceChannel`` so existing
callers (voice presenters, macro chains, input channel error paths) do not
need to change, while the voice output path stays unified under the Channel
abstraction.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Active Volcengine Dialogue WS Clients (keyed by thread_id).
# Managed by app.api.routes.voice_ws; VoiceChannel reads this registry for TTS.
active_volc_clients: dict[str, Any] = {}


async def push_voice_result(
    thread_id: str, status: str, summary: str, *, skip_tts: bool = False
) -> None:
    """Push a voice route result (done/failed/routed/cancelled) to the WS."""
    from app.core.channel.output.voice_channel import VoiceChannel

    await VoiceChannel.push_voice_result(thread_id, status, summary, skip_tts=skip_tts)


async def push_voice_token(thread_id: str, token: str, _index: int) -> None:
    """Push a streaming TTS token for real-time playback."""
    from app.core.channel.output.voice_channel import VoiceChannel

    await VoiceChannel.push_voice_token(thread_id, token, _index)


async def push_voice_tts_boundary(thread_id: str, sentence: str, index: int) -> None:
    """Push a TTS sentence boundary for real-time playback."""
    from app.core.channel.output.voice_channel import VoiceChannel

    await VoiceChannel.push_voice_tts_boundary(thread_id, sentence, index)


async def push_tts_text(thread_id: str, text: str) -> None:
    """Send confirmation/result text to Volcengine Dialogue TTS."""
    from app.core.channel.output.voice_channel import VoiceChannel

    await VoiceChannel.push_tts_text(thread_id, text)


# ── 宏执行 ──────────────────────────────


async def maybe_push_tts(thread_id: str, text: str) -> None:
    """推确认语——统一走 VoiceChannel TTS 路径。"""
    from app.core.channel.output.voice_channel import VoiceChannel

    await VoiceChannel.push_tts_text(thread_id, text)


async def push_macro_result(thread_id: str, status: str, summary: str) -> None:
    """Push a macro result back to the voice WS."""
    from app.core.channel.output.voice_channel import VoiceChannel

    await VoiceChannel.push_macro_result(thread_id, status, summary)


async def handle_navigate(
    route: str, thread_id: str, feedback: str | None = None
) -> None:
    """Send a frontend navigation command via voice WS."""
    from app.core.channel.output.voice_channel import VoiceChannel

    await VoiceChannel.handle_navigate(route, thread_id, feedback=feedback)


async def push_local_result(thread_id: str, action: str, args: Any) -> None:
    """Push an L0 local result back to the voice WS."""
    from app.core.channel.output.voice_channel import VoiceChannel

    await VoiceChannel.push_local_result(thread_id, action, args)
