"""
VoiceChannel — pushes agent results to the voice WebSocket for TTS playback.

Handles message types from the ChannelRegistry (selected upstream by OutputChannelPolicy):

1. ``MessageBlock(role=ai, content=...)`` — the main Agent's 安抚话术 (its
   first visible response, e.g. "好的，我来处理").  Pushed as
   ``voice.route_result {routed, text}`` for immediate TTS.

2. ``SessionCompletedEvent(source=voice)`` — terminal success. Pushed as
   ``voice.route_result {done, summary}``.

3. ``AgentRunCompletedEvent(source=voice, status=failed)`` — terminal failure.
   Pushed as ``voice.route_result {failed, error}``.

4. ``TokenEvent`` — streaming LLM tokens from the main Agent.  Accumulated
   and pushed to Volcengine ChatTTSText progressively.

Streaming TTS via TokenEvent:
- As LLM tokens arrive (TokenEvent), text accumulates in `_tts_accumulator`.
- At each sentence boundary (。！？.!?\n…), complete sentences are pushed to
  Volcengine ChatTTSText progressively: first chunk `start=True,end=False`,
  subsequent `start=False,end=False`.
- On SessionCompletedEvent, any remainder is flushed with `end=True`.
- This gives true streaming send + streaming playback.

Note: OutputChannelPolicy is the authoritative source of voice channel selection.
The source checks below are defense-in-depth in case a caller bypasses policy.
This class is also the single owner of the voice WebSocket transport; legacy
helpers in ``app.core.voice.executor`` delegate here rather than pushing directly.
"""

import asyncio
import logging
import re
import time
from typing import Any

from app.core.engine.message.schemas import MessageBlock
from app.core.routing.routing_data import get_store
from app.core.schemas.canonical import Endpoint, MessageType, create_envelope
from app.core.voice import executor as voice_executor
from app.core.voice.state_machine import VoiceSessionState, voice_state_machine
from app.utils.text import strip_markdown_for_tts
from app.utils.time import elapsed_ms

from ..base import Channel, ChannelContext

logger = logging.getLogger(__name__)


class VoiceChannel(Channel):
    """Relays agent events to the voice WebSocket for TTS."""

    name = "voice"
    accepts_blocks = True
    accepts_stream_events = True

    # Runtime WebSocket transport dependencies, wired once at startup by main.py.
    _manager: Any = None
    _envelope_fn: Any = None
    _message_type: Any = None

    # Per-thread dedup for 安抚话术 (main Agent first response)
    _filler_texts: dict[str, set[str]] = {}
    _token_buffers: dict[str, str] = {}
    _streamed_texts: dict[str, str] = {}
    _boundary_index: dict[str, int] = {}
    _SENTENCE_BOUNDARIES = "。！？.!?\n…"

    # Streaming TTS state: push to Volcengine progressively
    _tts_accumulator: dict[str, str] = {}
    _tts_started: dict[str, bool] = {}
    _cancelled_threads: set[str] = set()

    # ── WebSocket transport binding & low-level push helpers ─────────────────
    # These used to live in app.core.voice.executor; they were moved here so
    # VoiceChannel is the single owner of voice WS output. Legacy callers in
    # executor/voice_input delegate to these methods instead of pushing directly.

    @classmethod
    def bind(cls, manager: Any, envelope_fn: Any, message_type: Any) -> None:
        """Wire WS transport dependencies at application startup.

        ``envelope_fn`` must return a JSON-serializable dict (not a Pydantic
        model). The caller is responsible for calling ``model_dump()`` if needed.
        """
        cls._manager = manager
        cls._envelope_fn = envelope_fn
        cls._message_type = message_type

    @classmethod
    def _voice_envelope(cls, msg_type: Any, body: dict) -> dict:
        """Fallback canonical envelope with voice-chain endpoint identity.

        Used only when ``_envelope_fn``/``_message_type`` were not wired at
        startup; produces the same 7-field shape (including source/target) as
        the wired path so the voice WS never receives a bare body dict.
        """
        return create_envelope(
            type=msg_type,
            body=body,
            source=Endpoint(kind="backend"),
            target=Endpoint(kind="voice"),
        ).model_dump()

    @classmethod
    async def push_voice_result(
        cls,
        thread_id: str,
        status: str,
        summary: str,
        *,
        skip_tts: bool = False,
    ) -> None:
        """Push a voice route result (done/failed/routed/cancelled) to the WS.

        ``_envelope_fn`` must return a JSON-serializable dict (not a Pydantic
        model) so the transport layer never has to guess the serialization path.
        """
        if cls._manager is None:
            logger.warning("[VoiceChannel] manager not set, cannot push result")
            return
        body = {
            "thread_id": thread_id,
            "status": status,
            "summary": summary,
            "skip_tts": skip_tts,
        }
        if cls._envelope_fn and cls._message_type:
            env = cls._envelope_fn(cls._message_type.VOICE_ROUTE_RESULT, body)
            await cls._manager.push(thread_id, env)
        else:
            await cls._manager.push(
                thread_id,
                cls._voice_envelope(MessageType.VOICE_ROUTE_RESULT, body),
            )

        if summary and status == "done" and not skip_tts:
            await cls.push_tts_text(thread_id, summary)

    @classmethod
    async def push_voice_token(cls, thread_id: str, token: str, _index: int) -> None:
        """Push a streaming TTS token for real-time playback."""
        if cls._manager is None:
            return
        body = {"thread_id": thread_id, "token": token}
        if cls._envelope_fn and cls._message_type:
            env = cls._envelope_fn(cls._message_type.VOICE_TOKEN, body)
            await cls._manager.push(thread_id, env)
        else:
            await cls._manager.push(
                thread_id,
                cls._voice_envelope(MessageType.VOICE_TOKEN, body),
            )

    @classmethod
    async def push_voice_tts_boundary(
        cls, thread_id: str, sentence: str, index: int
    ) -> None:
        """Push a TTS sentence boundary for real-time playback."""
        if cls._manager is None:
            return
        body = {"thread_id": thread_id, "sentence": sentence, "index": index}
        if cls._envelope_fn and cls._message_type:
            env = cls._envelope_fn(cls._message_type.VOICE_TTS_BOUNDARY, body)
            await cls._manager.push(thread_id, env)
        else:
            await cls._manager.push(
                thread_id,
                cls._voice_envelope(MessageType.VOICE_TTS_BOUNDARY, body),
            )

    @classmethod
    async def push_tts_text(cls, thread_id: str, text: str) -> None:
        """Send confirmation/result text to Volcengine Dialogue TTS."""
        client = voice_executor.active_volc_clients.get(thread_id)
        if not client:
            return
        if client.ws is None:
            try:
                await client.reconnect()
            except Exception as e:
                logger.error("[VoiceChannel] push_tts_text reconnect failed: %s", e)
                return
        try:
            from app.api.routes.voice_ws import unblock_voice_tts

            unblock_voice_tts(thread_id)
        except ImportError:
            pass
        try:
            await client.send_chat_tts_text(start=True, end=False, content=text)
            await client.send_chat_tts_text(start=False, end=True, content="")
            logger.info(
                "[VoiceChannel] push_tts_text sent %d chars to thread %s",
                len(text),
                thread_id,
            )
        except Exception as exc:
            logger.error("[VoiceChannel] push_tts_text failed: %s", exc)

    @classmethod
    async def push_macro_result(cls, thread_id: str, status: str, summary: str) -> None:
        """Push a macro result back to the voice WS (reuses voice.route_result)."""
        if cls._manager is None:
            logger.warning("[VoiceChannel] manager not set, cannot push macro result")
            return
        body = {"thread_id": thread_id, "status": status, "summary": summary}
        if cls._envelope_fn and cls._message_type:
            env = cls._envelope_fn(cls._message_type.VOICE_ROUTE_RESULT, body)
            await cls._manager.push(thread_id, env)
        else:
            await cls._manager.push(
                thread_id,
                cls._voice_envelope(MessageType.VOICE_ROUTE_RESULT, body),
            )
        await cls._set_idle_if_needed(thread_id)

    @classmethod
    async def push_local_result(cls, thread_id: str, action: str, args: Any) -> None:
        """Push an L0 local action result back to the voice WS."""
        if cls._manager is None:
            logger.warning("[VoiceChannel] manager not set, cannot push local result")
            return
        body = {
            "thread_id": thread_id,
            "status": "routed",
            "target": {"type": "local", "action": action},
            "params": args or {},
            "candidates": [],
        }
        if cls._envelope_fn and cls._message_type:
            env = cls._envelope_fn(cls._message_type.VOICE_ROUTE_RESULT, body)
            await cls._manager.push(thread_id, env)
        else:
            await cls._manager.push(
                thread_id,
                cls._voice_envelope(MessageType.VOICE_ROUTE_RESULT, body),
            )
        await cls._set_idle_if_needed(thread_id)

    @classmethod
    async def handle_navigate(
        cls, route: str, thread_id: str, feedback: str | None = None
    ) -> None:
        """Send a frontend navigation command via voice WS, with optional TTS."""
        logger.info(
            "[VoiceChannel] handle_navigate route=%s thread=%s feedback=%s",
            route,
            thread_id,
            feedback,
        )
        if cls._manager is None:
            logger.warning("[VoiceChannel] manager not set, cannot push navigate")
            return
        if feedback is None:
            _routing_store = get_store()
            feedback = _routing_store.responses.get("generic", {}).get("ok", "")
        body = {"route": route, "thread_id": thread_id, "feedback": feedback}
        if cls._envelope_fn and cls._message_type:
            await cls._manager.push(
                thread_id,
                cls._envelope_fn(MessageType.VOICE_NAVIGATE, body),
            )
        else:
            await cls._manager.push(
                thread_id,
                cls._voice_envelope(MessageType.VOICE_NAVIGATE, body),
            )
        await cls.push_tts_text(thread_id, feedback)
        await cls._set_idle_if_needed(thread_id)

    @classmethod
    async def _set_idle_if_needed(cls, thread_id: str) -> None:
        """Transition the voice state machine back to IDLE if not already."""
        current = await voice_state_machine.get(thread_id)
        if current != VoiceSessionState.IDLE:
            await voice_state_machine.set(thread_id, VoiceSessionState.IDLE)

    @classmethod
    def reset_tts_started(cls, thread_id: str) -> None:
        cls._tts_started.pop(thread_id, None)

    @classmethod
    def reset_thread(cls, thread_id: str) -> None:
        """Clear per-thread streaming TTS state for a new turn."""
        cls._cancelled_threads.discard(thread_id)
        cls._tts_accumulator.pop(thread_id, None)
        cls._tts_started.pop(thread_id, None)
        cls._token_buffers.pop(thread_id, None)
        cls._streamed_texts.pop(thread_id, None)
        cls._boundary_index.pop(thread_id, None)
        cls._filler_texts.pop(thread_id, None)

    @classmethod
    def cancel_thread(cls, thread_id: str) -> bool:
        """Cancel any in-flight streaming TTS for a thread.

        Returns True if a streaming TTS segment was active and had to be
        aborted.
        """
        was_streaming = cls._tts_started.pop(thread_id, False)
        if not was_streaming:
            # No active TTS segment to cancel; do not mark the thread as
            # cancelled so a new turn's result is not suppressed.
            return False
        cls._tts_accumulator.pop(thread_id, None)
        cls._token_buffers.pop(thread_id, None)
        cls._streamed_texts.pop(thread_id, None)
        cls._boundary_index.pop(thread_id, None)
        cls._filler_texts.pop(thread_id, None)
        cls._cancelled_threads.add(thread_id)
        return was_streaming

    @classmethod
    async def _push_speaking_state(cls, thread_id: str) -> None:
        """Notify the client that TTS playback started (HUD switches to speaking view)."""
        if cls._manager is None:
            return
        body = {"state": "speaking", "thread_id": thread_id}
        if cls._envelope_fn and cls._message_type:
            env = cls._envelope_fn(cls._message_type.VOICE_STATE, body)
            await cls._manager.push(thread_id, env)
        else:
            await cls._manager.push(
                thread_id, cls._voice_envelope(MessageType.VOICE_STATE, body)
            )

    @classmethod
    async def push_tts_chunk(
        cls, thread_id: str, text: str, end: bool, *, force_start: bool = False
    ) -> None:
        """Push a text chunk to Volcengine ChatTTSText with correct start/end.

        Args:
            force_start: If True, treat this as the start of a new TTS segment
                         (used by confirmation TTS from L0 macros).
        """
        from app.core.voice.executor import active_volc_clients

        if thread_id in cls._cancelled_threads:
            return

        client = active_volc_clients.get(thread_id)
        if not client:
            logger.debug("[VoiceChannel][tts-chunk] no volc client for %s", thread_id)
            return

        if force_start:
            start = True
            cls._tts_started[thread_id] = True
        else:
            started = cls._tts_started.get(thread_id, False)
            start = not started
            cls._tts_started[thread_id] = True

        if start:
            if not force_start:
                await voice_state_machine.set(thread_id, VoiceSessionState.SPEAKING)
                await cls._push_speaking_state(thread_id)
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
            from app.api.routes.voice_ws import unblock_voice_tts

            unblock_voice_tts(thread_id)
        except ImportError:
            pass

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
            token = payload.content or ""
            if not token:
                return
            if tid in self.__class__._cancelled_threads:
                # barge-in 已取消旧流：TTS 已停，也不再推送 token/boundary 事件
                return

            # Accumulate for dedup
            self._streamed_texts[tid] = self._streamed_texts.get(tid, "") + token
            # Accumulate transcript (used by the final boundary flush)
            self._token_buffers[tid] = self._token_buffers.get(tid, "") + token

            # Push a streaming token event (实时播报文本，前端可据此显示字幕)
            try:
                await VoiceChannel.push_voice_token(
                    tid, token, len(self._streamed_texts[tid])
                )
            except Exception as exc:
                logger.debug(
                    "[VoiceChannel] push voice.token failed for %s: %s", tid, exc
                )

            # Accumulate for streaming TTS
            buf = self._tts_accumulator.get(tid, "") + token

            # Split on sentence boundaries; push complete sentences, keep remainder
            parts = re.split(r"(?<=[。！？.!?\n…])", buf)
            if len(parts) > 1:
                # parts[:-1] are complete sentences, parts[-1] is remainder
                complete = "".join(parts[:-1])
                remaining = parts[-1]
                clean = strip_markdown_for_tts(complete).strip()
                if clean:
                    await self.__class__.push_tts_chunk(tid, clean, end=False)
                    # Push a sentence-boundary event (前端可据此做分段/字幕同步)
                    idx = self._boundary_index.get(tid, 0)
                    try:
                        await VoiceChannel.push_voice_tts_boundary(tid, clean, idx)
                        self._boundary_index[tid] = idx + 1
                    except Exception as exc:
                        logger.debug(
                            "[VoiceChannel] push voice.tts_boundary failed for %s: %s",
                            tid,
                            exc,
                        )
                buf = remaining

            self._tts_accumulator[tid] = buf
            return

        # ── 主 Agent 安抚话术（首个可见回应）：推送 routed 事件 ──
        if isinstance(payload, MessageBlock):
            if not payload.is_visible:
                logger.debug(
                    "[VoiceChannel] skip hidden MessageBlock for %s", ctx.thread_id
                )
                return
            if payload.role == "ai" and payload.content:
                tid = ctx.thread_id

                streamed = self._streamed_texts.get(tid, "").strip()
                summary = "" if streamed else strip_markdown_for_tts(payload.content)

                tid_set = self._filler_texts.setdefault(tid, set())
                clean_summary = summary.replace(" ", "").replace("\n", "")
                if clean_summary and clean_summary in tid_set:
                    logger.info(
                        "[VoiceChannel] 安抚话术 dedup: already routed for %s", tid
                    )
                    return
                if not clean_summary:
                    # token 已流式播报（summary 为空）时不再推送空的 routed 结果，
                    # 否则会在最终 done 前产生冗余的空 route_result（测试/前端
                    # 取到它会误以为中间态，且 UI 收到空文案）。
                    return
                tid_set.add(clean_summary)

                # Fire-and-forget: don't block callback chain if WS send is congested
                async def _push_routed():
                    try:
                        await VoiceChannel.push_voice_result(tid, "routed", summary)
                    except Exception as exc:
                        logger.warning(
                            "[VoiceChannel] 安抚话术 push failed for %s: %s", tid, exc
                        )

                asyncio.create_task(_push_routed())
            return

        # ── 最终回复 ──────────────────────────────────────────
        if isinstance(payload, SessionCompletedEvent):
            thread_id = payload.thread_id
            was_cancelled = thread_id in self.__class__._cancelled_threads
            self.__class__._cancelled_threads.discard(thread_id)
            self._filler_texts.pop(thread_id, None)
            data = payload.data
            # Defense-in-depth: policy should already filter non-voice sessions.
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
                clean = strip_markdown_for_tts(rem)
                if clean:
                    await self.__class__.push_tts_chunk(thread_id, clean, end=True)
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

            # Flush remaining tokens in buffer (final boundary for the last fragment)
            remaining_buf = strip_markdown_for_tts(
                self._token_buffers.pop(thread_id, "")
            )
            if remaining_buf:
                try:
                    idx = self._boundary_index.get(thread_id, 0)
                    await VoiceChannel.push_voice_tts_boundary(
                        thread_id, remaining_buf, idx
                    )
                    self._boundary_index.pop(thread_id, None)
                except Exception as exc:
                    logger.debug("[VoiceChannel] flush tts_boundary failed: %s", exc)

            push_text = (data.tts_summary or data.summary or "").strip()
            streamed_text = self._streamed_texts.pop(thread_id, "").strip()
            final_text = strip_markdown_for_tts(push_text)

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
            await VoiceChannel.push_voice_result(
                thread_id, "done", final_text, skip_tts=True
            )
            elapsed = elapsed_ms(t0)
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
            # Defense-in-depth: policy should already filter non-voice sessions.
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
                await VoiceChannel.push_voice_result(thread_id, "failed", summary)
            except Exception as exc:
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
