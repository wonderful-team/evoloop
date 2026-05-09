"""
Transparent Callback Handler with Structured Streaming
=======================================================

Unified callback handler with structured stream events.
Eliminates separate EnhancedStreamManager module by integrating its capabilities directly.
"""

import ast
import json
import logging
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.engine.callbacks.token_filter import TokenFilter
from app.core.engine.message import MessageHandler, MessagePublisher
from app.core.engine.message.reasoning import extract_reasoning_from_kwargs
from app.core.tools.registry import (
    get_tool_affected_paths,
    get_tool_metadata,
    is_state_mutating_tool,
)

logger = logging.getLogger(__name__)


class TransparentCallbackHandler(AsyncCallbackHandler):
    """
    Unified CallbackHandler with structured streaming support.

    Responsibilities:
    1. LangChain callback handling (on_llm_start, on_tool_end, etc.)
    2. Cancellation checking and special tool notifications
    3. Structured stream event publishing (thinking only)
    """

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

        # Stream tracking
        self._token_filter = TokenFilter()
        self._publisher: MessagePublisher | None = None
        self._thinking_buffer: str = ""  # Accumulated reasoning content for real-time streaming

        # Node-level streaming control: run_id -> metadata mapping
        self._run_metadata: dict[str, dict] = {}

    # ==============================================================================
    # Structured Stream Event Methods
    # ==============================================================================

    # --------------------------------------------------------------------------
    # Streaming Helpers
    # --------------------------------------------------------------------------

    async def emit_thinking(self, content: str):
        """发送 AI 思考过程片段"""
        if not self.thread_id:
            return

        await MessageHandler.stream_thinking(self.thread_id, content)

    # ==============================================================================
    # LangChain Callback Methods
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

        Strategy:
        - THINKING (reasoning_content): stream per-chunk in real-time
        - CONTENT: batch through TokenFilter (flush on \n or 50 chars)
        """
        run_id = str(kwargs.get("run_id", ""))
        if self._is_streaming_disabled(run_id):
            return

        if not (self.thread_id and self.monitor):
            return

        await self.monitor.check_cancellation(self.thread_id)

        if not (self.llm_task_id and run_id == str(self.active_llm_run_id)):
            return

        # 1. Extract and stream reasoning_content in real-time (accumulated)
        generation_chunk = kwargs.get("chunk")
        if generation_chunk and hasattr(generation_chunk, "message"):
            msg_chunk = generation_chunk.message
            delta_reasoning = extract_reasoning_from_kwargs(msg_chunk.additional_kwargs)
            if delta_reasoning:
                self._thinking_buffer += delta_reasoning
                # 直接通过 Handler 流式推送思考片段
                await self.emit_thinking(delta_reasoning)

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

        # Content goes through TokenFilter (hidden-tag suppression)
        filtered, _ = self._token_filter.process(token)
        if filtered is None:
            # Inside hidden tag — don't publish
            return

        # NEW: Publish the filtered token to the frontend
        if filtered:
            await MessageHandler.stream_token(self.thread_id, filtered)

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        run_id = str(kwargs.get("run_id", ""))
        self._run_metadata.pop(run_id, None)

        # FLUSH REMAINING PUBLISH BUFFER
        self._token_filter.flush()

        # Reset accumulated thinking buffer for the next LLM call
        self._thinking_buffer = ""

        # Note: We no longer record "Thinking..." steps, so no update needed
        if run_id == str(self.active_llm_run_id):
            self.active_llm_run_id = None
            self._token_filter.reset()

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when LLM errors."""
        run_id = str(kwargs.get("run_id", ""))
        logger.error(f"LLM Error in thread {self.thread_id}: {error}", exc_info=True)

        # Flush any buffered tokens before cleanup
        self._token_filter.flush()

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

        tool_name = serialized.get("name") or "Unknown Tool"
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
                message=f"Executing {tool_name}...",
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
                        try:
                            await self.monitor.update_agent_state(self.thread_id, mode, tname, tstatus)
                        except Exception:
                            pass

            if is_state_mutating_tool(tool_name):
                if isinstance(data, dict):
                    affected_paths = get_tool_affected_paths(tool_name, data)
                    if affected_paths:
                        fname = affected_paths[0]
                        try:
                            await self.monitor.add_artifact(
                                self.thread_id,
                                fname.split("/")[-1],
                                "file",
                                "pending",
                                fname,
                            )
                        except Exception:
                            pass

            if metadata.get("is_memory_tool"):
                args = data if isinstance(data, dict) else {}
                action = args.get("action", "")
                key = args.get("key") or args.get("query") or args.get("name") or "Unknown"
                memory_name = f"{action or tool_name}: {key[:30]}"
                try:
                    await self.monitor.set_active_memory(self.thread_id, f"tool-{tool_name}", memory_name)
                except Exception:
                    pass

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
                message=f"Completed {tool_name}",
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
                message=f"Failed {tool_name}: {str(error)}",
                status="failed"
            )

    async def on_chain_start(self, serialized: dict[str, Any], inputs: dict[str, Any], **kwargs: Any) -> None:
        """Run when chain (node) starts running.
        
        Note: We no longer record Phase headers ("► Supervisor Phase", etc.) to reduce noise.
        Only actual tool executions are tracked.
        """
        run_id = str(kwargs.get("run_id", ""))
        self._run_metadata[run_id] = kwargs.get("metadata", {})

    async def on_chain_end(self, outputs: dict[str, Any], **kwargs: Any) -> None:
        """Run when chain ends running.
        
        Note: Phase headers tracking removed, this is now a no-op.
        """
        run_id = str(kwargs.get("run_id", ""))
        self._run_metadata.pop(run_id, None)

    async def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when chain errors.
        
        Note: Phase headers tracking removed, this is now a no-op.
        """
        run_id = str(kwargs.get("run_id", ""))
        self._run_metadata.pop(run_id, None)

    async def on_text(self, text: str, **kwargs: Any) -> None:
        """Run on arbitrary text."""
        logger.info(f"[Text] {text}")
