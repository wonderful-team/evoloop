"""
Transparent Callback Handler with Structured Streaming
=======================================================

Unified callback handler with structured stream events.
Eliminates separate EnhancedStreamManager module by integrating its capabilities directly.
"""

import ast
import json
import logging
import time
from typing import Any

from app.core.engine.callbacks.base import AsyncCallbackHandler, LLMResult
from app.core.engine.callbacks.token_filter import TokenFilter
from app.core.engine.message import MessageHandler, MessagePublisher
from app.core.engine.message.reasoning import extract_reasoning_from_kwargs
from app.core.tools.registry import (
    get_tool_affected_paths,
    get_tool_metadata,
    is_state_mutating_tool,
)
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


class TransparentCallbackHandler(AsyncCallbackHandler):
    """
    Unified CallbackHandler with structured streaming support.

    Responsibilities:
    1. Callback handling (on_llm_start, on_tool_end, etc.)
    2. Cancellation checking and special tool notifications
    3. Structured stream event publishing (thinking only)
    """

    # Dual-limit flush: time window (s) or char count threshold
    _FLUSH_INTERVAL = 0.5
    _FLUSH_CHAR_LIMIT = 30

    def __init__(self, thread_id: str = ""):
        super().__init__()
        self.thread_id = thread_id
        from app.core.context import tool_state_store
        from app.core.monitoring.activity import activity_monitor

        self.monitor = activity_monitor
        self._tool_store = tool_state_store

        # Step tracking
        self.llm_task_id = None
        self.active_llm_run_id = None
        self._tool_names: dict[str, str] = {}  # run_id -> tool_name mapping for parallel tools

        # Throttle cancellation checks during high-frequency streaming
        self._cancellation_check_counter = 0
        self._CANCELLATION_CHECK_INTERVAL = 50  # check every N tokens

        # Stream tracking
        self._token_filter = TokenFilter()
        self._publisher: MessagePublisher | None = None
        self._thinking_buffer: str = ""  # Accumulated reasoning content for real-time streaming

        # Dual-limit flush state
        self._flush_start_time: float | None = None  # time.time() when current batch started

        # Node-level streaming control: run_id -> metadata mapping
        self._run_metadata: dict[str, dict] = {}

    # ==============================================================================
    # Structured Stream Event Methods
    # ==============================================================================

    # --------------------------------------------------------------------------
    # Streaming Helpers
    # --------------------------------------------------------------------------

    async def emit_thinking(self, content: str, message_id: str | None = None):
        """发送 AI 思考过程片段"""
        if not self.thread_id:
            return

        await MessageHandler.stream_thinking(self.thread_id, content, message_id=message_id)

    # ==============================================================================
    # Callback Methods
    # ==============================================================================

    def _is_streaming_disabled(self, run_id: str) -> bool:
        """Check if the run's node has streaming disabled via metadata."""
        metadata = self._run_metadata.get(run_id, {})
        if metadata.get("streaming") is False:
            return True
        return False

    async def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        """Run when LLM starts running."""
        run_id = kwargs.get("run_id")
        run_id_str = str(run_id)
        self._run_metadata[run_id_str] = kwargs.get("metadata", {})

        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

            if self.active_llm_run_id is None:
                self.active_llm_run_id = run_id
            self.llm_task_id = run_id

            # Skip thinking indicator for nodes with streaming disabled
            if self._is_streaming_disabled(run_id_str):
                return

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Run on new LLM token.

        Uses dual-limit flush strategy:
        - Time window (1s): guarantees frontend sees content promptly
        - Token count (100): batches aggressively during steady output
        """
        run_id = str(kwargs.get("run_id", ""))
        if self._is_streaming_disabled(run_id):
            return

        if not (self.thread_id and self.monitor):
            return

        # Throttle cancellation checks: do not hit the DB for every single token.
        self._cancellation_check_counter += 1
        if self._cancellation_check_counter % self._CANCELLATION_CHECK_INTERVAL == 0:
            await self.monitor.check_cancellation(self.thread_id)

        if not (self.llm_task_id and run_id == str(self.active_llm_run_id)):
            return

        now = time.time()
        if self._flush_start_time is None:
            self._flush_start_time = now

        def _should_flush(buffer: str) -> bool:
            return bool(buffer) and (
                len(buffer) >= self._FLUSH_CHAR_LIMIT
                or (now - self._flush_start_time) >= self._FLUSH_INTERVAL
            )

        # 1. Extract and stream reasoning_content (dual-limit flush)
        generation_chunk = kwargs.get("chunk")
        is_tool_call = False
        if generation_chunk and hasattr(generation_chunk, "message"):
            msg_chunk = generation_chunk.message
            is_tool_call = bool(msg_chunk.tool_calls)

            # Extract standard reasoning content
            delta_reasoning = extract_reasoning_from_kwargs(msg_chunk.additional_kwargs)
            if delta_reasoning:
                self._thinking_buffer += delta_reasoning

            # Extract Anthropic native thinking if present
            if isinstance(msg_chunk.content, list):
                for block in msg_chunk.content:
                    if isinstance(block, dict) and block.get("type") == "thinking" and "thinking" in block:
                        self._thinking_buffer += block["thinking"]
            elif isinstance(msg_chunk.content, dict) and msg_chunk.content.get("type") == "thinking" and "thinking" in msg_chunk.content:
                self._thinking_buffer += msg_chunk.content["thinking"]

            if _should_flush(self._thinking_buffer):
                await self.emit_thinking(self._thinking_buffer, message_id=run_id)
                self._thinking_buffer = ""
                self._flush_start_time = now

        # Prevent tool call JSON arguments from leaking into the plain text stream
        if is_tool_call:
            return

        # 2. Defensive: normalize structured tokens
        if not isinstance(token, str):
            if isinstance(token, list):
                parts = []
                for t in token:
                    if isinstance(t, dict):
                        if "partial_json" in t:
                            parts.append(t["partial_json"])
                        elif "text" in t:
                            parts.append(t["text"])
                    else:
                        parts.append(str(t))
                token = "".join(parts)
            elif isinstance(token, dict):
                token = token.get("partial_json") or token.get("text") or ""
            else:
                token = str(token)

        # 3. Content goes through TokenFilter (hidden-tag suppression + buffer)
        filtered, _ = self._token_filter.process(token)
        if filtered is None:
            return

        # Dual-limit flush: size check (chars), time check externally
        if self._token_filter.should_flush(char_limit=self._FLUSH_CHAR_LIMIT) or (
            self._flush_start_time and (now - self._flush_start_time) >= self._FLUSH_INTERVAL
        ):
            batch = self._token_filter.flush()
            if batch:
                await MessageHandler.stream_token(self.thread_id, batch, message_id=run_id)
                self._flush_start_time = now

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        run_id = str(kwargs.get("run_id", ""))
        self._run_metadata.pop(run_id, None)

        # FLUSH REMAINING THINKING BUFFER
        if self._thinking_buffer:
            await self.emit_thinking(self._thinking_buffer, message_id=run_id)
            self._thinking_buffer = ""

        # FLUSH REMAINING TOKEN BUFFER
        remaining = self._token_filter.flush()
        if remaining:
            await MessageHandler.stream_token(self.thread_id, remaining, message_id=run_id)

        # Note: We no longer record "Thinking..." steps, so no update needed
        if run_id == str(self.active_llm_run_id):
            self.active_llm_run_id = None
            self._token_filter.reset()

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when LLM errors."""
        run_id = str(kwargs.get("run_id", ""))
        logger.error(f"LLM Error in thread {self.thread_id}: {error}", exc_info=True)

        # FLUSH REMAINING THINKING BUFFER
        if self._thinking_buffer:
            await self.emit_thinking(self._thinking_buffer, message_id=run_id)
            self._thinking_buffer = ""

        # FLUSH REMAINING TOKEN BUFFER
        remaining = self._token_filter.flush()
        if remaining:
            await MessageHandler.stream_token(self.thread_id, remaining, message_id=run_id)

        if run_id == str(self.active_llm_run_id):
            self.active_llm_run_id = None
            self._token_filter.reset()

        if self._is_streaming_disabled(run_id):
            self._run_metadata.pop(run_id, None)
            return

        self._run_metadata.pop(run_id, None)

        logger.info(f"[LLM Error] {error}")

    async def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Run when tool starts running."""
        run_id = str(kwargs.get("run_id", "default"))
        self._run_metadata[run_id] = kwargs.get("metadata", {})

        if self._is_streaming_disabled(run_id):
            return

        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

        # 兼容不同的序列化结构
        tool_name = (
            serialized.get("name") or
            serialized.get("kwargs", {}).get("name") or
            "Unknown Tool"
        )
        self._tool_names[run_id] = tool_name

        # Get tool metadata
        metadata = get_tool_metadata(tool_name) or {}
        is_hidden = metadata.get("is_hidden", False)

        # Parse input data first (fixes pre-existing use-before-assign bug)
        data = None
        if input_str.strip().startswith("{"):
            try:
                data = json.loads(input_str)
            except (json.JSONDecodeError, ValueError):
                pass
        if data is None and input_str.strip().startswith("{"):
            try:
                data = ast.literal_eval(input_str)
            except (ValueError, SyntaxError):
                pass

        # Phase 2-3: Step tracking and StreamEvent removed — StepEvent now driven by MessageHandler
        # Extract path info
        current_tool_path = None
        if data and isinstance(data, dict):
            affected_paths = get_tool_affected_paths(tool_name, data)
            if affected_paths:
                current_tool_path = affected_paths[0]

        # Store tool state in shared store
        if self.thread_id:
            self._tool_store.start_tool(
                thread_id=self.thread_id,
                run_id=run_id,
                name=tool_name,
                arguments=input_str,
                path=current_tool_path
            )

        logger.info(f"[Tool Start] {tool_name} {'(hidden)' if is_hidden else ''}")

        # Stream real-time progress for visible tools
        if self.thread_id and not is_hidden:
            await MessageHandler.stream_progress(
                self.thread_id,
                message=i18n.get("evoloop.tool_summary.running_tool", tool=tool_name, input=input_str[:100]),
                metadata={"tool_name": tool_name}
            )

        # Handle special tool types (only applies to visible tools)
        if self.thread_id:
            if tool_name == "task_boundary":
                if isinstance(data, dict):
                    mode = data.get("Mode")
                    tname = data.get("TaskName")
                    tstatus = data.get("TaskStatus")
                    if mode and tname:
                        await self.monitor.update_agent_state(self.thread_id, mode, tname, tstatus)

            if is_state_mutating_tool(tool_name):
                if isinstance(data, dict):
                    affected_paths = get_tool_affected_paths(tool_name, data)
                    if affected_paths:
                        fname = affected_paths[0]
                        await self.monitor.add_artifact(
                            self.thread_id,
                            fname.split("/")[-1],
                            "file",
                            "pending",
                            fname,
                        )

            if metadata.get("is_memory_tool"):
                args = data if isinstance(data, dict) else {}
                action = args.get("action", "")
                key = args.get("key") or args.get("query") or args.get("name") or "Unknown"
                memory_name = f"{action or tool_name}: {key[:30]}"
                await self.monitor.set_active_memory(self.thread_id, f"tool-{tool_name}", memory_name)

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Run when tool ends running."""
        run_id = str(kwargs.get("run_id", "default"))

        if self._is_streaming_disabled(run_id):
            self._run_metadata.pop(run_id, None)
            self._tool_names.pop(run_id, None)
            return

        self._run_metadata.pop(run_id, None)

        tool_name = self._tool_names.pop(run_id, "Unknown Tool")

        # Get tool state from shared store
        if self.thread_id:
            self._tool_store.end_tool(self.thread_id, run_id)

        # Phase 2-3: Step tracking and StreamEvent removed — StepEvent now driven by MessageHandler
        logger.info(f"[Tool End] {tool_name}")

        if self.thread_id:
            await MessageHandler.stream_progress(
                self.thread_id,
                message=i18n.get("evoloop.tool_summary.file_op_result"),
                status="success"
            )

    async def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when tool errors."""
        run_id = str(kwargs.get("run_id", "default"))

        if self._is_streaming_disabled(run_id):
            self._run_metadata.pop(run_id, None)
            self._tool_names.pop(run_id, None)
            return

        self._run_metadata.pop(run_id, None)

        tool_name = self._tool_names.pop(run_id, "Unknown Tool")
        logger.info(f"[Tool Error] {tool_name}: {error}")

        if self.thread_id:
            await MessageHandler.stream_progress(
                self.thread_id,
                message=i18n.get("common.tool_execution_error", name=tool_name, error=str(error)),
                status="failed"
            )
