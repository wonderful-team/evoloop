"""
VoiceChannel — pushes agent results to the voice WebSocket for TTS playback.

Handles three message types from the UniversalBridgeSubscriber:

1. ``MessageBlock(role=ai, content=..., tool_calls=[...])`` — the Supervisor's
   acknowledgement when it routes to a Worker (e.g. "好的，我来处理").
   Pushed as ``voice.route_result {routed, text}`` for immediate TTS.

2. ``SessionCompletedEvent(source=voice)`` — terminal success. Pushed as
   ``voice.route_result {done, summary}``.

3. ``AgentRunCompletedEvent(source=voice, status=failed)`` — terminal failure.
   Pushed as ``voice.route_result {failed, error}``.

Only the FIRST ai+tool_calls block per thread/turn is pushed (voice_ack_sent
tracking). Subsequent blocks (Worker messages) are ignored.
"""

import logging
import re
import time
from typing import Any

from app.core.engine.message.schemas import MessageBlock
from app.core.routing import executor as voice_executor

from ..base import Channel, ChannelContext

logger = logging.getLogger(__name__)

# Markdown symbols that TTS cannot render — strip before push
_MD_CLEAN_RE = re.compile(r'(\*\*|__|`|#{1,6}\s*|>\s*|[-*]\s)')


def _md_clean(text: str) -> str:
    """Strip markdown formatting that would be spoken verbatim in TTS."""
    return _MD_CLEAN_RE.sub('', text)


class VoiceChannel(Channel):
    """Relays agent events to the voice WebSocket for TTS."""

    name = "voice"
    accepts_blocks = True
    accepts_stream_events = True

    # Per-thread token buffer for sentence-level segmenting
    _token_buffers: dict[str, str] = {}
    _streamed_texts: dict[str, str] = {}
    _SENTENCE_BOUNDARIES = "。！？.!?\n…"

    async def send(self, payload: Any, ctx: ChannelContext) -> None:
        from app.core.events.schemas.lifecycle import SessionCompletedEvent
        from app.core.engine.event.schemas import AgentRunCompletedEvent
        from app.models.schemas.events import TokenEvent

        # ── LLM Token streaming ──────────────────────────────────────────
        if isinstance(payload, TokenEvent):
            tid = ctx.thread_id
            from app.core.routing.executor import _voice_registry
            if tid not in _voice_registry:
                return

            token = payload.content or ""
            if not token:
                return

            # Accumulate token
            self._streamed_texts[tid] = self._streamed_texts.get(tid, "") + token
            buf = self._token_buffers.get(tid, "") + token
            self._token_buffers[tid] = buf

            # Push raw voice token (optional, index=0)
            try:
                await voice_executor.push_voice_token(tid, token, 0)
            except Exception as exc:
                logger.debug("[VoiceChannel] token push failed: %s", exc)

            # Check sentence boundary
            if any(ch in self._SENTENCE_BOUNDARIES for ch in token):
                stripped = _md_clean(buf.strip())
                if stripped:
                    try:
                        await voice_executor.push_voice_tts_boundary(tid, stripped, 0)
                    except Exception as exc:
                        logger.warning("[VoiceChannel] tts_boundary push failed: %s", exc)
                self._token_buffers[tid] = ""
            return

        # ── Supervisor acknowledgement (role=ai + content) ─────────────
        if isinstance(payload, MessageBlock):
            if payload.role == "ai" and payload.content:
                tid = ctx.thread_id
                # Only push for voice-sourced threads
                from app.core.routing.executor import _voice_registry
                if tid not in _voice_registry:
                    return

                # Avoid double-speaking streamed ack sentences
                streamed = self._streamed_texts.get(tid, "").strip()
                summary = "" if streamed else _md_clean(payload.content)

                try:
                    await voice_executor.push_voice_result(tid, "routed", summary)
                except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
                    logger.warning("[VoiceChannel] ack push failed for %s: %s", tid, exc)
            return

        # ── Terminal success ──────────────────────────────────────────
        if isinstance(payload, SessionCompletedEvent):
            data = payload.data
            if not data or data.source != "voice":
                return
            thread_id = payload.thread_id

            # Flush remaining tokens in buffer
            remaining_buf = _md_clean(self._token_buffers.pop(thread_id, "").strip())
            if remaining_buf:
                try:
                    await voice_executor.push_voice_tts_boundary(thread_id, remaining_buf, 0)
                except Exception as exc:
                    logger.debug("[VoiceChannel] flush tts_boundary failed: %s", exc)

            # Use tts_summary for TTS. Fallback: first sentence of summary only.
            push_text = data.tts_summary if data.tts_summary else ""
            if not push_text and data.summary:
                first = re.split(r"[。！？.!?\n]", data.summary)[0].strip()
                if first:
                    push_text = first + "。"

            # Check if this text was already streamed and spoken
            streamed_text = self._streamed_texts.pop(thread_id, "")
            clean_push = push_text.strip().replace(" ", "").replace("\n", "")
            clean_streamed = streamed_text.strip().replace(" ", "").replace("\n", "")
            if clean_push and clean_push in clean_streamed:
                push_text = ""

            final_text = _md_clean(push_text)

            t0 = time.time()
            started_at = data.duration_ms or 0
            try:
                await voice_executor.push_voice_result(thread_id, "done", final_text)
                elapsed = (time.time() - t0) * 1000
                logger.info(
                    "[voice-perf] %s agent_done push=%.0fms agent_duration=%.0fms",
                    thread_id, elapsed, started_at,
                )
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
                logger.warning("[VoiceChannel] done push failed for %s: %s", thread_id, exc)
            return

        # ── Terminal failure ──────────────────────────────────────────
        if isinstance(payload, AgentRunCompletedEvent):
            if payload.status == "done":
                return
            if payload.source != "voice":
                return
            thread_id = payload.thread_id
            self._token_buffers.pop(thread_id, None)
            self._streamed_texts.pop(thread_id, None)
            summary = payload.payload.get("summary") or payload.payload.get("outcome") or ""
            try:
                await voice_executor.push_voice_result(thread_id, "failed", summary)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
                logger.warning("[VoiceChannel] failed push failed for %s: %s", thread_id, exc)
            return

    async def send_envelope(
        self,
        env_type: str,
        body: dict[str, Any],
        target_device_key: str | None = None,
        member_id: int = 0,
    ) -> None:
        return
