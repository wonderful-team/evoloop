"""
VoiceChannel — pushes agent results to the voice WebSocket for TTS playback.

Handles three message types from the UniversalBridgeSubscriber:

1. ``MessageBlock(role=ai, content=..., tool_calls=[...])`` — the Supervisor's
   安抚话术 when it routes to a Worker (e.g. "好的，我来处理").
   Pushed as ``voice.route_result {routed, text}`` for immediate TTS.

2. ``SessionCompletedEvent(source=voice)`` — terminal success. Pushed as
   ``voice.route_result {done, summary}``.

3. ``AgentRunCompletedEvent(source=voice, status=failed)`` — terminal failure.
   Pushed as ``voice.route_result {failed, error}``.

Only the FIRST ai+tool_calls block per thread/turn is pushed (安抚话术已发送
tracking). Subsequent blocks (Worker messages) are ignored.

Streaming TTS via TokenEvent:
- As LLM tokens arrive (TokenEvent), text accumulates in `_tts_accumulator`.
- At each sentence boundary (。！？.!?\n…), complete sentences are pushed to
  Volcengine ChatTTSText progressively: first chunk `start=True,end=False`,
  subsequent `start=False,end=False`.
- On SessionCompletedEvent, any remainder is flushed with `end=True`.
- This gives true streaming send + streaming playback.
"""

import asyncio
import logging
import re
import time
from typing import Any

from app.core.engine.message.schemas import MessageBlock
from app.core.voice import executor as voice_executor
from app.core.voice.state_machine import VoiceSessionState, voice_state_machine

from ..base import Channel, ChannelContext

logger = logging.getLogger(__name__)

# Markdown cleanup for TTS — remove formatting that would be read verbatim.
# This is NOT truncation; it only strips markdown syntax and normalizes whitespace.


def _md_clean(text: str) -> str:
    """Strip markdown formatting that would be spoken verbatim in TTS."""
    if not text:
        return text

    # 1. Images: keep alt text if present, otherwise remove.
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # 2. Links: keep link text only.
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # 3. Bold, italic, strikethrough, inline code markers.
    text = re.sub(r"\*\*|\*|__|_|~~|`", "", text)
    # 4. Heading markers.
    text = re.sub(r"#{1,6}\s*", "", text)
    # 5. Blockquote markers.
    text = re.sub(r">\s*", "", text)
    # 6. Numbered list markers.
    text = re.sub(r"\d+\.\s+", "", text)
    # 7. Bullet list markers.
    text = re.sub(r"[-*+]\s+", "", text)
    # 8. Table pipes.
    text = re.sub(r"\|", "", text)
    # 9. Horizontal rules.
    text = re.sub(r"^\s*[-*_]{2,}\s*$", "", text, flags=re.MULTILINE)
    # 10. Normalize excessive whitespace.
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


class VoiceChannel(Channel):
    """Relays agent events to the voice WebSocket for TTS."""

    name = "voice"
    accepts_blocks = True
    accepts_stream_events = True

    # Per-thread dedup for 安抚话术 (Supervisor first response)
    _filler_texts: dict[str, set[str]] = {}
    _token_buffers: dict[str, str] = {}
    _streamed_texts: dict[str, str] = {}
    _SENTENCE_BOUNDARIES = "。！？.!?\n…"

    # Streaming TTS state: push to Volcengine progressively
    _tts_accumulator: dict[str, str] = {}
    _tts_started: dict[str, bool] = {}
    _cancelled_threads: set[str] = set()

    @classmethod
    def reset_thread(cls, thread_id: str) -> None:
        """Clear per-thread streaming TTS state for a new turn."""
        cls._cancelled_threads.discard(thread_id)
        cls._tts_accumulator.pop(thread_id, None)
        cls._tts_started.pop(thread_id, None)
        cls._token_buffers.pop(thread_id, None)
        cls._streamed_texts.pop(thread_id, None)
        cls._filler_texts.pop(thread_id, None)

    @classmethod
    def cancel_thread(cls, thread_id: str) -> bool:
        """Cancel any in-flight streaming TTS for a thread.

        Returns True if a streaming TTS segment was active and had to be
        aborted.
        """
        was_streaming = cls._tts_started.pop(thread_id, False)
        cls._tts_accumulator.pop(thread_id, None)
        cls._token_buffers.pop(thread_id, None)
        cls._streamed_texts.pop(thread_id, None)
        cls._filler_texts.pop(thread_id, None)
        cls._cancelled_threads.add(thread_id)
        return was_streaming

    async def push_tts_chunk(
        self, thread_id: str, text: str, end: bool, *, force_start: bool = False
    ) -> None:
        """Push a text chunk to Volcengine ChatTTSText with correct start/end.

        Args:
            force_start: If True, treat this as the start of a new TTS segment
                         (used by confirmation TTS from L0 macros).
        """
        from app.core.voice.executor import active_volc_clients

        if thread_id in self._cancelled_threads:
            return

        client = active_volc_clients.get(thread_id)
        if not client:
            logger.debug("[VoiceChannel][tts-chunk] no volc client for %s", thread_id)
            return

        if force_start:
            start = True
            self._tts_started[thread_id] = True
        else:
            started = self._tts_started.get(thread_id, False)
            start = not started
            self._tts_started[thread_id] = True

        if start:
            if not force_start:
                await voice_state_machine.set(thread_id, VoiceSessionState.SPEAKING)
            # flag 在 voice_receive_loop 的 Event 350 中清，这里不清

        logger.info(
            "[VoiceChannel][tts-chunk] %s start=%s end=%s [%d chars] content=%r",
            thread_id,
            start,
            end,
            len(text),
            text[:80] + "..." if len(text) > 80 else text,
        )
        try:
            await client.send_chat_tts_text(start=start, end=end, content=text)
        except Exception as exc:
            logger.error(
                "[VoiceChannel][tts-chunk] push failed for %s: %s", thread_id, exc
            )

    async def send(self, payload: Any, ctx: ChannelContext) -> None:
        from app.core.engine.event.schemas import AgentRunCompletedEvent
        from app.core.events.schemas.lifecycle import SessionCompletedEvent
        from app.models.schemas.events import TokenEvent

        if isinstance(payload, TokenEvent):
            tid = ctx.thread_id
            from app.core.voice.executor import _voice_registry

            if tid not in _voice_registry:
                return
            token = payload.content or ""
            if not token:
                return

            # Accumulate for dedup
            self._streamed_texts[tid] = self._streamed_texts.get(tid, "") + token

            # Accumulate for streaming TTS
            buf = self._tts_accumulator.get(tid, "") + token

            # Split on sentence boundaries; push complete sentences, keep remainder
            parts = re.split(r"(?<=[。！？.!?\n…])", buf)
            if len(parts) > 1:
                # parts[:-1] are complete sentences, parts[-1] is remainder
                complete = "".join(parts[:-1])
                remaining = parts[-1]
                clean = _md_clean(complete).strip()
                if clean:
                    await self.push_tts_chunk(tid, clean, end=False)
                buf = remaining

            self._tts_accumulator[tid] = buf
            return

        # ── Superviosr 安抚话术：首个回应时推送 ────────────────
        if isinstance(payload, MessageBlock):
            if not payload.is_visible:
                logger.debug(
                    "[VoiceChannel] skip hidden MessageBlock for %s", ctx.thread_id
                )
                return
            if payload.role == "ai" and payload.content:
                tid = ctx.thread_id
                from app.core.voice.executor import _voice_registry

                if tid not in _voice_registry:
                    return

                streamed = self._streamed_texts.get(tid, "").strip()
                summary = "" if streamed else _md_clean(payload.content)

                tid_set = self._filler_texts.setdefault(tid, set())
                clean_summary = summary.replace(" ", "").replace("\n", "")
                if clean_summary and clean_summary in tid_set:
                    logger.info(
                        "[VoiceChannel] 安抚话术 dedup: already routed for %s", tid
                    )
                    return
                if clean_summary:
                    tid_set.add(clean_summary)

                # Fire-and-forget: don't block callback chain if WS send is congested
                async def _push_routed():
                    try:
                        await voice_executor.push_voice_result(tid, "routed", summary)
                    except (
                        ValueError,
                        OSError,
                        RuntimeError,
                        TypeError,
                        KeyError,
                    ) as exc:
                        logger.warning(
                            "[VoiceChannel] 安抚话术 push failed for %s: %s", tid, exc
                        )

                asyncio.create_task(_push_routed())
            return

        # ── 最终回复 ──────────────────────────────────────────
        if isinstance(payload, SessionCompletedEvent):
            thread_id = payload.thread_id
            was_cancelled = thread_id in self._cancelled_threads
            self._cancelled_threads.discard(thread_id)
            self._filler_texts.pop(thread_id, None)
            data = payload.data
            if not data or data.source != "voice":
                return

            # If this turn was barge-in cancelled, do not flush stale TTS or
            # push a done result.
            if was_cancelled:
                self._tts_accumulator.pop(thread_id, None)
                self._tts_started.pop(thread_id, None)
                self._streamed_texts.pop(thread_id, None)
                self._token_buffers.pop(thread_id, None)
                return

            # Flush remaining TTS accumulator with end=True
            rem = self._tts_accumulator.pop(thread_id, "").strip()
            if rem:
                clean = _md_clean(rem)
                if clean:
                    await self.push_tts_chunk(thread_id, clean, end=True)
            else:
                # If accumulator is empty but streaming started, send empty end marker
                if self._tts_started.get(thread_id, False):
                    logger.info(
                        "[VoiceChannel][tts-chunk] %s end=True (empty flush)", thread_id
                    )
                    try:
                        from app.core.voice.executor import active_volc_clients

                        client = active_volc_clients.get(thread_id)
                        if client:
                            await client.send_chat_tts_text(
                                start=False, end=True, content=""
                            )
                    except Exception as exc:
                        logger.warning(
                            "[VoiceChannel][tts-chunk] empty end failed: %s", exc
                        )

            self._tts_started.pop(thread_id, None)

            # Flush remaining tokens in buffer
            remaining_buf = _md_clean(self._token_buffers.pop(thread_id, "").strip())
            if remaining_buf:
                try:
                    await voice_executor.push_voice_tts_boundary(
                        thread_id, remaining_buf, 0
                    )
                except Exception as exc:
                    logger.debug("[VoiceChannel] flush tts_boundary failed: %s", exc)

            push_text = (data.tts_summary or data.summary or "").strip()
            streamed_text = self._streamed_texts.pop(thread_id, "").strip()
            final_text = _md_clean(push_text)

            logger.info(
                "[VoiceChannel] done: push_text=%r, streamed_text=%r (len_push=%d, len_streamed=%d)",
                push_text,
                streamed_text,
                len(push_text),
                len(streamed_text),
            )

            # Send status=done WS message via the shared helper, but skip the
            # confirmation TTS path because streaming TTS is already handled.
            t0 = time.time()
            await voice_executor.push_voice_result(
                thread_id, "done", final_text, skip_tts=True
            )
            elapsed = (time.time() - t0) * 1000
            logger.info(
                "[voice-perf] %s agent_done push=%.0fms agent_duration=%.0fms",
                thread_id,
                elapsed,
                data.duration_ms or 0,
            )
            return

        # ── Terminal failure ──────────────────────────────────────────
        if isinstance(payload, AgentRunCompletedEvent):
            if payload.status == "done":
                return
            if payload.source != "voice":
                return
            thread_id = payload.thread_id
            self._cancelled_threads.discard(thread_id)
            self._token_buffers.pop(thread_id, None)
            self._streamed_texts.pop(thread_id, None)
            self._filler_texts.pop(thread_id, None)
            self._tts_accumulator.pop(thread_id, None)
            self._tts_started.pop(thread_id, None)
            summary = (
                payload.payload.get("summary") or payload.payload.get("outcome") or ""
            )
            try:
                await voice_executor.push_voice_result(thread_id, "failed", summary)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
                logger.warning(
                    "[VoiceChannel] failed push failed for %s: %s", thread_id, exc
                )
            return

    async def send_envelope(
        self,
        env_type: str,
        body: dict[str, Any],
        target_device_key: str | None = None,
        member_id: int = 0,
    ) -> None:
        return
