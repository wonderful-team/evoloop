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
from pydantic import Field

from app.core.engine.callbacks.token_filter import TokenFilter
from app.core.engine.message.reasoning import extract_reasoning_from_kwargs
from app.core.tools.registry import (
    get_tool_affected_paths,
    get_tool_metadata,
    is_state_mutating_tool,
)
from app.i18n.service import i18n
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.events import StreamEventType
from app.utils.time import format_iso_timestamp

logger = logging.getLogger(__name__)


from app.core.engine.message.publisher import MessagePublisher
from app.core.engine.message.schemas import (
    StreamEvent, 
    ThinkingPayload, 
    ToolProgressPayload
)


class TransparentCallbackHandler(AsyncCallbackHandler):
    """
    Unified CallbackHandler with structured streaming support.
    

    Stream event capabilities are now integrated directly into this handler.
    
    Responsibilities:
    1. LangChain callback handling (on_llm_start, on_tool_end, etc.)
    2. Activity monitor integration (step tracking)
    3. Structured stream event publishing (thinking, tool_progress, etc.)
    """

    def __init__(self, thread_id: str = None):
        super().__init__()
        self.thread_id = thread_id
        from app.core.context import tool_state_store
        from app.core.monitoring.activity import activity_monitor

        self.monitor = activity_monitor
        self._tool_store = tool_state_store

        # Step tracking
        self.llm_task_id = None
        self.tool_task_id = None  # Legacy: single tool task (for sync compatibility)
        self._tool_task_ids: dict[str, int] = {}  # run_id -> task_id mapping for parallel tools
        self.active_llm_run_id = None
        self._tool_names: dict[str, str] = {}  # run_id -> tool_name mapping for parallel tools

        # Stream tracking
        self._current_stream_buffer = ""
        self._token_filter = TokenFilter()
        self._publisher: MessagePublisher | None = None

    # ==============================================================================
    # Structured Stream Event Methods
    # ==============================================================================

    async def _publish_stream_event(self, event: StreamEvent):
        """
        Publish a structured stream event to EventBus for frontend SSE consumption.
        """
        if not self._publisher:
            self._publisher = MessagePublisher(thread_id=self.thread_id)
        
        await self._publisher.publish(event)

    async def emit_thinking(self, message: str, detail: str = "reasoning"):
        """Emit thinking/reasoning event."""
        await self._publish_stream_event(StreamEvent(
            type=StreamEventType.THINKING,
            message=message,
            data=ThinkingPayload(detail=detail)
        ))

    async def emit_tool_progress(self, tool_name: str, message: str, progress: int | None = None):
        """Emit tool progress update."""
        await self._publish_stream_event(StreamEvent(
            type=StreamEventType.TOOL_PROGRESS,
            message=message,
            data=ToolProgressPayload(tool=tool_name),
            progress=progress
        ))

    async def emit_checkpoint(self, checkpoint_id: int, name: str, file_count: int):
        """Emit checkpoint creation event."""
        await self._publish_stream_event(StreamEvent(
            type=StreamEventType.CHECKPOINT,
            message=f"Checkpoint created: {name}",
            data={"checkpoint_id": checkpoint_id, "file_count": file_count}
        ))

    # ==============================================================================
    # LangChain Callback Methods
    # ==============================================================================

    async def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        """Run when LLM starts running."""
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

            run_id = kwargs.get("run_id")
            if self.active_llm_run_id is None:
                self.active_llm_run_id = run_id
            self.llm_task_id = run_id

            # Emit thinking indicator so frontend shows loading state
            try:
                await self.emit_thinking(" reasoning...", detail="AI is analyzing the request")
            except Exception:
                pass

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Run on new LLM token.

        Strategy:
        - THINKING (reasoning_content): stream per-chunk in real-time
        - CONTENT: batch through TokenFilter (flush on \n or 50 chars)
        """
        if not (self.thread_id and self.monitor):
            return

        await self.monitor.check_cancellation(self.thread_id)

        run_id = kwargs.get("run_id")
        if not (self.llm_task_id and run_id == self.active_llm_run_id):
            return

        # 1. Extract and stream reasoning_content in real-time (chunk-level)
        generation_chunk = kwargs.get("chunk")
        if generation_chunk and hasattr(generation_chunk, "message"):
            msg_chunk = generation_chunk.message
            reasoning = extract_reasoning_from_kwargs(getattr(msg_chunk, "additional_kwargs", None))
            if reasoning:
                await self._publish_stream_event(StreamEvent(
                    type=StreamEventType.THINKING,
                    message=reasoning,
                    data={"detail": "reasoning"}
                ))

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

        self._current_stream_buffer += token

        # 3. Content goes through TokenFilter (hidden-tag suppression + batch flush)
        filtered, _ = self._token_filter.process(token)
        if filtered is None:
            # Inside hidden tag — update step but don't publish
            return

        if self._token_filter.should_flush():
            buf = self._token_filter.flush()
            # Note: We no longer stream AI content tokens to support block-based message delivery.
            # Thinking content still streams via StreamEventType.THINKING above.
            # if buf and self.thread_id:
            #     try:
            #         from app.core.engine.message.handler import MessageHandler
            #         await MessageHandler.stream_token(self.thread_id, buf)
            #     except Exception:
            #         pass

            try:
                await self.monitor.update_step(
                    self.thread_id,
                    self.llm_task_id,
                    "running",
                    details=self._current_stream_buffer,
                )
            except Exception:
                pass

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        # FLUSH REMAINING PUBLISH BUFFER
        self._token_filter.flush()

        run_id = kwargs.get("run_id")
        # Note: We no longer record "Thinking..." steps, so no update needed
        if run_id == self.active_llm_run_id:
            self.active_llm_run_id = None
            self._current_stream_buffer = ""
            self._token_filter.reset()

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when LLM errors."""
        logger.error(f"LLM Error in thread {self.thread_id}: {error}", exc_info=True)

        # Flush any buffered tokens before cleanup
        buf = self._token_filter.flush()
        # Note: We no longer stream AI content tokens to support block-based message delivery.
        # if buf and self.thread_id:
        #     try:
        #         from app.core.engine.message.handler import MessageHandler
        #         await MessageHandler.stream_token(self.thread_id, buf)
        #     except Exception:
        #         pass

        run_id = kwargs.get("run_id")
        if run_id == self.active_llm_run_id:
            self.active_llm_run_id = None
            self._current_stream_buffer = ""
            self._token_filter.reset()

        try:
            await self._publish_stream_event(StreamEvent(
                type=StreamEventType.TOOL_ERROR,
                message=str(error),
                data={"source": "llm", "success": False}
            ))
            logger.info(f"[TransparentCallback] Published error event for thread {self.thread_id}")
        except Exception as e:
            logger.error(f"[TransparentCallback] Failed to publish error event for thread {self.thread_id}: {e}")

    async def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Run when tool starts running."""
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

        run_id = str(kwargs.get("run_id", "default"))
        tool_name = serialized.get("name") if serialized else "Unknown Tool"
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

        from app.core.tools.registry import get_tool_friendly_name
        friendly_name = get_tool_friendly_name(tool_name)

        # Build display name (parameterized, e.g. "正在读取 '/path/to/file'")
        tool_name_display = None
        summary_template = metadata.get("summary_template")
        if summary_template:
            try:
                args_dict = data if isinstance(data, dict) else {}
                tool_name_display = i18n.get(summary_template, **args_dict)
            except (KeyError, TypeError):
                pass

        # Skip ActivityMonitor and stream events for hidden (internal) tools
        run_id = str(kwargs.get("run_id", "default"))
        step_type = "tool"
        if not is_hidden and self.thread_id and self.monitor:
            task_id = await self.monitor.add_step(
                self.thread_id,
                friendly_name,
                step_type,
                input_data=data,
                tool_name_display=tool_name_display,
            )
            self.tool_task_id = task_id
            self._tool_task_ids[run_id] = task_id

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

        # Emit structured stream event — include tool_name_display for frontend
        if not is_hidden:
            await self._publish_stream_event(StreamEvent(
                type=StreamEventType.TOOL_START,
                message=friendly_name,
                data={"tool": tool_name, "tool_name_display": tool_name_display, "params": data}
            ))

        logger.info(f"[Tool Start] {tool_name} {'(hidden)' if is_hidden else ''}")

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
        tool_name = self._tool_names.pop(run_id, "Unknown Tool")

        # Get the correct task_id for this tool run (support parallel tools)
        task_id = self._tool_task_ids.pop(run_id, None)

        # Check if tool is hidden (internal)
        metadata = get_tool_metadata(tool_name) or {}
        is_hidden = metadata.get("is_hidden", False)

        # Get tool state from shared store
        tool_state = None
        if self.thread_id:
            tool_state = self._tool_store.end_tool(self.thread_id, run_id)

        # Ensure output is string for fallback and logging
        output_str = str(output) if not isinstance(output, str) else output

        if tool_state:
            log_output, _ = tool_state.get_summary(output)
            duration = self._tool_store.get_duration(self.thread_id, run_id) if self.thread_id else None
        else:
            # Fallback if state not found
            log_output = output_str[:500] if len(output_str) > 500 else output_str
            duration = None

        log_output_str = str(log_output) if not isinstance(log_output, str) else log_output

        if not is_hidden and self.thread_id and task_id:
            await self.monitor.update_step(self.thread_id, task_id, "done", details=log_output_str)
            # Clear legacy single tool tracking if it matches
            if self.tool_task_id == task_id:
                self.tool_task_id = None

        logger.info(f"[Tool End] {tool_name} {'(hidden)' if is_hidden else ''}")

        if not is_hidden and tool_name:
            await self._publish_stream_event(StreamEvent(
                type=StreamEventType.TOOL_COMPLETE,
                message=log_output_str[:200],
                data={"tool": tool_name, "duration": duration, "success": True}
            ))

    async def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when tool errors."""
        run_id = str(kwargs.get("run_id", "default"))
        tool_name = self._tool_names.pop(run_id, "Unknown Tool")

        # Get the correct task_id for this tool run (support parallel tools)
        task_id = self._tool_task_ids.pop(run_id, None)

        # Check if tool is hidden (internal)
        metadata = get_tool_metadata(tool_name) or {}
        is_hidden = metadata.get("is_hidden", False)

        if not is_hidden and self.thread_id and task_id and self.monitor:
            exc_name = type(error).__name__
            if "Interrupt" in exc_name or "GraphInterrupt" in exc_name:
                await self.monitor.update_step(self.thread_id, task_id, "done")
            else:
                await self.monitor.update_step(self.thread_id, task_id, "failed", details=str(error))

            # Clear legacy single tool tracking if it matches
            if self.tool_task_id == task_id:
                self.tool_task_id = None

        if not is_hidden and tool_name:
            await self._publish_stream_event(StreamEvent(
                type=StreamEventType.TOOL_ERROR,
                message=str(error)[:200],
                data={"tool": tool_name, "success": False}
            ))

    async def on_chain_start(self, serialized: dict[str, Any], inputs: dict[str, Any], **kwargs: Any) -> None:
        """Run when chain (node) starts running.
        
        Note: We no longer record Phase headers ("► Supervisor Phase", etc.) to reduce noise.
        Only actual tool executions are tracked.
        """
        # Phase headers tracking removed - only track actual tool executions
        pass

    async def on_chain_end(self, outputs: dict[str, Any], **kwargs: Any) -> None:
        """Run when chain ends running.
        
        Note: Phase headers tracking removed, this is now a no-op.
        """
        pass

    async def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when chain errors.
        
        Note: Phase headers tracking removed, this is now a no-op.
        """
        pass

    async def on_text(self, text: str, **kwargs: Any) -> None:
        """Run on arbitrary text."""
        logger.info(f"[Text] {text}")
