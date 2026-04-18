"""
Transparent Callback Handler with Structured Streaming
=======================================================

Unified callback handler with structured stream events.
Eliminates separate EnhancedStreamManager module by integrating its capabilities directly.
"""

import ast
import json
import logging
from enum import Enum
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
from pydantic import Field

from app.core.tools.registry import (
    get_tool_affected_paths,
    get_tool_metadata,
    is_state_mutating_tool,
)
from app.i18n.service import i18n
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.events import TokenEvent

logger = logging.getLogger(__name__)


class StreamEventType(Enum):
    """Types of streaming events for real-time UI updates."""
    THINKING = "thinking"
    TOOL_START = "tool_start"
    TOOL_PROGRESS = "tool_progress"
    TOOL_COMPLETE = "tool_complete"
    TOOL_ERROR = "tool_error"
    CHECKPOINT = "checkpoint"
    PROGRESS = "progress"
    COMPLETE = "complete"


def _utc_now_iso() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat()


class StreamEvent(DynamicBaseModel):
    """A structured streaming event for frontend consumption."""
    type: str
    message: str
    data: dict | None = None
    progress: int | None = None
    timestamp: str = Field(default_factory=_utc_now_iso)

    def to_json(self) -> str:
        """Convert to JSON string for SSE."""
        return self.model_dump_json(exclude_none=True)


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
        from app.infrastructure.cache import cache

        self.monitor = activity_monitor
        self._cache = cache
        self._tool_store = tool_state_store

        # Step tracking
        self.llm_task_id = None
        self.tool_task_id = None  # Legacy: single tool task (for sync compatibility)
        self._tool_task_ids: dict[str, int] = {}  # run_id -> task_id mapping for parallel tools
        self.active_llm_run_id = None

        # Stream tracking
        self._current_stream_buffer = ""

    # ==============================================================================
    # Structured Stream Event Methods
    # ==============================================================================

    async def _publish_stream_event(self, event: StreamEvent):
        """
        Publish a structured stream event to cache for frontend SSE consumption.
        
        Unified with existing events channel (single channel architecture).
        All events (tokens, thinking, tool_progress) go through the same channel.
        """
        if not self.thread_id:
            return

        # Unified: Publish to events channel (same as TokenEvent)
        # Frontend distinguishes by event structure (type field)
        await self._cache.publish(
            f"chat:{self.thread_id}:events",
            event.to_json()
        )

    async def emit_thinking(self, message: str, detail: str | None = None):
        """Emit thinking/reasoning event."""
        await self._publish_stream_event(StreamEvent(
            type=StreamEventType.THINKING.value,
            message=message,
            data={"detail": detail} if detail else None
        ))

    async def emit_tool_progress(self, tool_name: str, message: str, progress: int | None = None):
        """Emit tool progress update."""
        await self._publish_stream_event(StreamEvent(
            type=StreamEventType.TOOL_PROGRESS.value,
            message=message,
            data={"tool": tool_name},
            progress=progress
        ))

    async def emit_checkpoint(self, checkpoint_id: int, name: str, file_count: int):
        """Emit checkpoint creation event."""
        await self._publish_stream_event(StreamEvent(
            type=StreamEventType.CHECKPOINT.value,
            message=f"Checkpoint created: {name}",
            data={"checkpoint_id": checkpoint_id, "file_count": file_count}
        ))

    # ==============================================================================
    # LangChain Callback Methods
    # ==============================================================================

    async def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        """Run when LLM starts running.
        
        Note: We no longer record "Thinking..." steps to reduce noise.
        Only actual tool executions are tracked.
        """
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

            # Deduplicate nested LLM calls
            if self.active_llm_run_id is None:
                self.active_llm_run_id = kwargs.get("run_id")
                # Removed: self.llm_task_id = await self.monitor.add_step(self.thread_id, "Thinking...", "ai")

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Run on new LLM token."""
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

            run_id = kwargs.get("run_id")
            if self.llm_task_id and run_id == self.active_llm_run_id:
                # Defensive: Handle structured tokens (Anthropic/Kimi sending dicts/lists)
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

                # --- NEW: Real-time Terminal Print for Debugging ---
                import sys
                sys.stdout.write(token)
                sys.stdout.flush()

                # --- 🏅 Token-level Technical Tag Filtering (Phase 5 UI Optimization) ---
                # We want to hide <evoloop_session_audit>...</evoloop_session_audit> and <think>...</think> from the user stream.
                # We also want to strip <evoloop_final_report> and </evoloop_final_report> tags but keep their content.

                if not hasattr(self, "_in_hidden_tag"):
                    self._in_hidden_tag = False
                if not hasattr(self, "_tag_buffer"):
                    self._tag_buffer = ""

                # Update tag buffer to detect tag boundaries
                self._tag_buffer += token
                if len(self._tag_buffer) > 100: # Safety cap
                    self._tag_buffer = self._tag_buffer[-100:]

                # 1. Detect start of hidden tags
                if not self._in_hidden_tag:
                    for tag in ["<evoloop_session_audit>", "<think>", "<thought>", "<evoloop_audit_outcome>", "<evoloop_audit_reason>", "<evoloop_audit_proof>"]:
                        if tag in self._tag_buffer:
                            self._in_hidden_tag = True
                            # The tokens that formed the tag shouldn't be published
                            # (Note: simpler to just stop publishing from this point)
                            break

                # 2. Detect end of hidden tags
                if self._in_hidden_tag:
                    for tag in ["</evoloop_session_audit>", "</think>", "</thought>", "</evoloop_audit_outcome>", "</evoloop_audit_reason>", "</evoloop_audit_proof>"]:
                        if tag in self._tag_buffer:
                            self._in_hidden_tag = False
                            self._tag_buffer = "" # Clear buffer after finding end tag
                            break

                    # While in hidden tag, we still update the step (for full history)
                    # but we don't ADD to the publish buffer.
                    return

                # 3. Strip <evoloop_final_report> and </evoloop_final_report> tags (just markers, content is welcome)
                content_to_stream = token
                if "<evoloop_final_report>" in content_to_stream:
                    content_to_stream = content_to_stream.replace("<evoloop_final_report>", "")
                if "</evoloop_final_report>" in content_to_stream:
                    content_to_stream = content_to_stream.replace("</evoloop_final_report>", "")

                # BUFFERED PUBLISH Strategy
                if not hasattr(self, "_publish_buffer"):
                    self._publish_buffer = ""

                self._publish_buffer += content_to_stream

                # Flush on Newline OR > 50 chars
                if "\n" in content_to_stream or len(self._publish_buffer) > 50:
                    if hasattr(self.monitor, "client") and self.monitor.client:
                        try:
                            await self.monitor.client.publish(
                                f"chat:{self.thread_id}:events",
                                TokenEvent(content=self._publish_buffer).json(),
                            )
                        except Exception:
                            pass
                    self._publish_buffer = ""

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
        # FLUSH REMAINING BUFFER
        if hasattr(self, "_publish_buffer") and self._publish_buffer:
            if self.thread_id and self.monitor and hasattr(self.monitor, "client"):
                try:
                    await self.monitor.client.publish(
                        f"chat:{self.thread_id}:events",
                        TokenEvent(content=self._publish_buffer).json(),
                    )
                except Exception:
                    pass
            self._publish_buffer = ""

        run_id = kwargs.get("run_id")
        # Note: We no longer record "Thinking..." steps, so no update needed
        if run_id == self.active_llm_run_id:
            self.active_llm_run_id = None
            self._current_stream_buffer = ""

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when LLM errors."""
        logger.error(f"LLM Error in thread {self.thread_id}: {error}", exc_info=True)

        run_id = kwargs.get("run_id")
        if run_id == self.active_llm_run_id:
            self.active_llm_run_id = None
            self._current_stream_buffer = ""

        # Emit structured stream event so the UI (steps area) shows failure
        try:
            await self._publish_stream_event(StreamEvent(
                type=StreamEventType.TOOL_ERROR.value,
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

        tool_name = serialized.get("name") if serialized else "Unknown Tool"
        self.current_tool_name = tool_name
        self.current_tool_path = None

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

        summary_template = metadata.get("summary_template")
        friendly_name = f"Using {tool_name}"
        if summary_template:
            try:
                args = data if isinstance(data, dict) else {}
                friendly_name = i18n.get(summary_template, **args)
            except (KeyError, TypeError):
                pass

        # Always write to ActivityMonitor for full runtime observability.
        # Hidden tools (e.g. route_to) use step_type="internal" so the system
        # can track them, but the UI layer can choose to filter them out.
        run_id = str(kwargs.get("run_id", "default"))
        step_type = "internal" if is_hidden else "tool"
        if self.thread_id and self.monitor:
            task_id = await self.monitor.add_step(self.thread_id, friendly_name, step_type, input_data=data)
            self.tool_task_id = task_id  # Legacy compatibility
            self._tool_task_ids[run_id] = task_id  # Track parallel tools by run_id

        # Extract path info (only for visible tools that may affect files)
        if data and isinstance(data, dict) and not is_hidden:
            affected_paths = get_tool_affected_paths(tool_name, data)
            if affected_paths:
                self.current_tool_path = affected_paths[0]

        # Store tool state in shared store
        if self.thread_id:
            self._tool_store.start_tool(
                thread_id=self.thread_id,
                run_id=run_id,
                name=tool_name,
                arguments=input_str,
                path=self.current_tool_path
            )

        # Emit structured stream event only for visible tools
        if not is_hidden:
            await self._publish_stream_event(StreamEvent(
                type=StreamEventType.TOOL_START.value,
                message=friendly_name,
                data={"tool": tool_name, "params": data}
            ))

        logger.info(f"[Tool Start] {tool_name} (hidden={is_hidden})")

        # Handle special tool types (only applies to visible tools)
        if self.thread_id and not is_hidden:
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
        tool_name = self.current_tool_name
        metadata = get_tool_metadata(tool_name) or {}
        is_hidden = metadata.get("is_hidden", False)

        # Get the correct task_id for this tool run (support parallel tools)
        run_id = str(kwargs.get("run_id", "default"))
        task_id = self._tool_task_ids.pop(run_id, None)

        if self.thread_id and task_id:
            await self.monitor.update_step(self.thread_id, task_id, "done")
            # Clear legacy single tool tracking if it matches
            if self.tool_task_id == task_id:
                self.tool_task_id = None

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

        logger.info(f"[Tool End] {tool_name} (hidden={is_hidden})")

        # Emit structured stream event only for visible tools
        if tool_name and not is_hidden:
            await self._publish_stream_event(StreamEvent(
                type=StreamEventType.TOOL_COMPLETE.value,
                message=log_output_str[:200],
                data={"tool": tool_name, "duration": duration, "success": True}
            ))

    async def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when tool errors."""
        tool_name = self.current_tool_name
        metadata = get_tool_metadata(tool_name) or {}
        is_hidden = metadata.get("is_hidden", False)

        logger.error(f"Tool Error in thread {self.thread_id}: {error}")

        # Get the correct task_id for this tool run (support parallel tools)
        run_id = str(kwargs.get("run_id", "default"))
        task_id = self._tool_task_ids.pop(run_id, None)

        if self.thread_id and task_id and self.monitor:
            exc_name = type(error).__name__
            if "Interrupt" in exc_name or "GraphInterrupt" in exc_name:
                await self.monitor.update_step(self.thread_id, task_id, "done")
            else:
                await self.monitor.update_step(self.thread_id, task_id, "failed", details=str(error))

            # Clear legacy single tool tracking if it matches
            if self.tool_task_id == task_id:
                self.tool_task_id = None

        # Emit structured stream event only for visible tools
        tool_name = getattr(self, 'current_tool_name', None)
        if tool_name and not is_hidden:
            await self._publish_stream_event(StreamEvent(
                type=StreamEventType.TOOL_ERROR.value,
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
