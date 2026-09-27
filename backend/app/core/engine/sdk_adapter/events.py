"""Translate SDK events into EvoLoop message/callback contracts."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)


def _content_to_text(message: Any) -> str:
    from openhands.sdk.llm import content_to_str

    return "".join(content_to_str(message.content))


def _tool_calls(message: Any) -> list[dict[str, Any]]:
    calls = []
    for call in message.tool_calls or []:
        if hasattr(call, "model_dump"):
            calls.append(call.model_dump(mode="json"))
        elif isinstance(call, dict):
            calls.append(call)
        else:
            calls.append({"id": str(call)})
    return calls


class SDKEventBridge:
    """Collect SDK events and schedule existing async message handlers."""

    def __init__(self, *, config: dict[str, Any], thread_id: str) -> None:
        self.config = config
        self.thread_id = thread_id
        self.loop = asyncio.get_running_loop()
        self.events: list[Any] = []
        self.summary = ""
        # DB 历史回放（_replay_state_history）会把旧消息事件灌回 SDK
        # EventLog；这些事件经 __call__ 会误触发落库/广播，造成旧 AI
        # 回复重复出现在消息流。回放期间置位本标志抑制桥接。
        self.replaying = False
        self._tasks: set[asyncio.Task[Any]] = set()

    async def start_llm_callbacks(self) -> None:
        """Emit ``on_llm_start`` to the legacy callback handlers.

        ``TransparentCallbackHandler.on_llm_new_token`` gates every token on
        ``llm_task_id``/``active_llm_run_id`` state that the legacy loop set up
        via ``on_llm_start`` — the SDK path must do the same or all streaming
        tokens are silently dropped.
        """

        run_id = str((self.config.get("configurable") or {}).get("run_id") or "")
        metadata = self.config.get("metadata") or {}
        for callback in self.config.get("callbacks") or []:
            start = getattr(callback, "on_llm_start", None)
            if start is None:
                continue
            task = self.loop.create_task(
                start({}, [], run_id=run_id, metadata=metadata)
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks))

    def __call__(self, event: Any) -> None:
        self.events.append(event)
        if self.replaying:
            return
        try:
            from openhands.sdk.event import MessageEvent

            if isinstance(event, MessageEvent) and event.source == "agent":
                if not event.llm_message.tool_calls:
                    self.summary = _content_to_text(event.llm_message)[-2000:]
                task = self.loop.create_task(self._persist_agent_message(event))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        except (ImportError, TypeError, AttributeError):
            logger.exception("Failed to bridge OpenHands SDK event")

    def on_token(self, chunk: Any) -> None:
        """Forward SDK streaming deltas into the legacy callback pipeline.

        SDK chunks are litellm ``ModelResponseStream`` (choices[0].delta) while
        the legacy handlers expect langchain-style ``.message`` chunks — split
        the delta here: ``reasoning_content`` goes to the thinking stream,
        ``content`` to the token stream, and tool-call argument deltas are
        suppressed exactly like the legacy loop.
        """

        callbacks = self.config.get("callbacks") or []
        if not callbacks:
            return
        choices = getattr(chunk, "choices", None) or []
        delta = getattr(choices[0], "delta", None) if choices else None
        if delta is None:
            return
        if getattr(delta, "tool_calls", None):
            return  # never leak tool-call JSON into the plain text stream

        # Tokens should be attributed to the real AI message that is being
        # generated, not the SDK run_id. The legacy callback pipeline stores
        # this id in ctx.last_ai_message_id during on_llm_start.
        from app.core.context.manager import ContextManager

        ctx = ContextManager.current()
        message_id = getattr(ctx, "last_ai_message_id", None) or ""
        reasoning = getattr(delta, "reasoning_content", None)
        content = getattr(delta, "content", None)
        if not reasoning and not content:
            return

        from app.core.engine.callbacks.bridge import emit_llm_new_token

        if reasoning:
            for callback in callbacks:
                emit_thinking = getattr(callback, "emit_thinking", None)
                if emit_thinking is None:
                    continue
                task = self.loop.create_task(
                    emit_thinking(str(reasoning), message_id=message_id)
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        if content:
            content_str = str(content)
            # Adapt to the legacy chunk shape: bridge.emit_llm_new_token wraps
            # chunk_msg in SimpleNamespace(message=...), so hand over the bare
            # message-level shape (content/additional_kwargs/tool_calls) — the
            # reasoning/tool-call split already happened above.
            legacy_msg = SimpleNamespace(
                content=content_str, additional_kwargs={}, tool_calls=[]
            )
            task = self.loop.create_task(
                emit_llm_new_token(callbacks, content_str, legacy_msg, message_id)
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _persist_agent_message(self, event: Any) -> None:
        handler = (self.config.get("configurable") or {}).get("message_handler")
        if handler is None:
            return

        message = event.llm_message
        thinking = event.reasoning_content or None

        # 结构化媒体引用直传：image/video 工具生成媒体时经 ctx 暂存引用，
        # 在此合并进 AI 消息的 references（不依赖模型在正文中复述链接）。
        from app.core.context.manager import ContextManager
        from app.core.engine.message.media_refs import consume_pending_media_refs

        ctx = ContextManager.current()
        extra_references = consume_pending_media_refs(ctx) if ctx else []

        # 先刷掉流式 token 缓冲，确保 tail token 在 completed AI 消息之前
        # 到达前端；否则 completed 消息先渲染，残留 token 随后才到。
        await self._flush_stream_buffers()
        await handler.handle_ai_message(
            content=_content_to_text(message),
            tool_calls=_tool_calls(message),
            thinking=thinking,
            metadata=self.config.get("metadata") or {},
            extra_references=extra_references,
        )

    async def _flush_stream_buffers(self) -> None:
        run_id = str((self.config.get("configurable") or {}).get("run_id") or "")
        for callback in self.config.get("callbacks") or []:
            flush = getattr(callback, "flush_stream_buffers", None)
            if flush is None:
                continue
            task = self.loop.create_task(flush(run_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def flush(self) -> None:
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks))
