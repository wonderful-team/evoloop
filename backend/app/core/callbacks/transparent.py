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
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.tools.registry import is_state_mutating_tool, get_tool_affected_paths, get_tool_metadata
from app.i18n.service import i18n
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


@dataclass
class StreamEvent:
    """A structured streaming event for frontend consumption."""
    type: str
    message: str
    data: dict | None = None
    progress: int | None = None
    timestamp: str | None = None
    
    def __post_init__(self):
        if self.timestamp is None:
            from datetime import datetime
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_json(self) -> str:
        """Convert to JSON string for SSE."""
        return json.dumps(asdict(self), default=str)


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
        from app.core.monitoring.activity import activity_monitor
        from app.core.context import tool_state_store
        from app.infrastructure.cache import cache

        self.monitor = activity_monitor
        self._cache = cache
        self._tool_store = tool_state_store
        
        # Step tracking
        self.llm_task_id = None
        self.tool_task_id = None
        self.active_llm_run_id = None
        self._current_phase_task_id = None
        self._active_nodes = {}
        
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
            
        try:
            # Unified: Publish to events channel (same as TokenEvent)
            # Frontend distinguishes by event structure (type field)
            await self._cache.publish(
                f"chat:{self.thread_id}:events",
                event.to_json()
            )
        except Exception as e:
            logger.debug(f"Failed to publish stream event: {e}")

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
        """Run when LLM starts running."""
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

            # Deduplicate nested LLM calls
            if self.active_llm_run_id is None:
                self.active_llm_run_id = kwargs.get("run_id")
                self.llm_task_id = await self.monitor.add_step(self.thread_id, "Thinking...", "ai")

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Run on new LLM token."""
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

            run_id = kwargs.get("run_id")
            if self.llm_task_id and run_id == self.active_llm_run_id:
                self._current_stream_buffer += token

                # BUFFERED PUBLISH Strategy
                if not hasattr(self, "_publish_buffer"):
                    self._publish_buffer = ""

                self._publish_buffer += token

                # Flush on Newline OR > 50 chars
                if "\n" in token or len(self._publish_buffer) > 50:
                    try:
                        if hasattr(self.monitor, "client") and self.monitor.client:
                            await self.monitor.client.publish(
                                f"chat:{self.thread_id}:events",
                                TokenEvent(content=self._publish_buffer).json(),
                            )
                        self._publish_buffer = ""

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
            try:
                if self.thread_id and self.monitor and hasattr(self.monitor, "client"):
                    await self.monitor.client.publish(
                        f"chat:{self.thread_id}:events",
                        TokenEvent(content=self._publish_buffer).json(),
                    )
            except Exception:
                pass
            self._publish_buffer = ""

        run_id = kwargs.get("run_id")
        if self.thread_id and self.llm_task_id and self.monitor:
            if run_id == self.active_llm_run_id:
                await self.monitor.update_step(self.thread_id, self.llm_task_id, "done")
                self.llm_task_id = None
                self.active_llm_run_id = None
                self._current_stream_buffer = ""

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when LLM errors."""
        logger.error(f"LLM Error in thread {self.thread_id}: {error}", exc_info=True)

        run_id = kwargs.get("run_id")
        if self.thread_id and self.llm_task_id and self.monitor:
            if run_id == self.active_llm_run_id:
                exc_name = type(error).__name__
                if "Interrupt" in exc_name or "GraphInterrupt" in exc_name:
                    await self.monitor.update_step(self.thread_id, self.llm_task_id, "done")
                else:
                    await self.monitor.update_step(self.thread_id, self.llm_task_id, "failed", details=str(error))
                
                self.llm_task_id = None
                self.active_llm_run_id = None
                self._current_stream_buffer = ""

    async def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Run when tool starts running."""
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

        tool_name = serialized.get("name") if serialized else "Unknown Tool"
        self.current_tool_name = tool_name
        self.current_tool_path = None

        # Get friendly name
        metadata = get_tool_metadata(tool_name) or {}
        summary_template = metadata.get("summary_template")
        
        friendly_name = f"Using {tool_name}"
        if summary_template:
            try:
                args = json.loads(input_str) if input_str.strip().startswith("{") else {}
                friendly_name = i18n.get(summary_template, **args)
            except Exception:
                pass

        # Create activity step
        if self.thread_id and self.monitor:
            parent_id = getattr(self, "_current_phase_task_id", None)
            if parent_id is None:
                parent_id = await self.monitor.add_step(self.thread_id, "► Execution Phase", "node")
                self._current_phase_task_id = parent_id

            self.tool_task_id = await self.monitor.add_step(self.thread_id, friendly_name, "tool", parent_id=parent_id)

        # Extract path info
        data = None
        try:
            if input_str.strip().startswith("{"):
                data = json.loads(input_str)
        except Exception:
            pass

        if data is None:
            try:
                if input_str.strip().startswith("{"):
                    data = ast.literal_eval(input_str)
            except Exception:
                pass

        if data and isinstance(data, dict):
            affected_paths = get_tool_affected_paths(tool_name, data)
            if affected_paths:
                self.current_tool_path = affected_paths[0]

        # Store tool state in shared store
        run_id = str(kwargs.get("run_id", "default"))
        if self.thread_id:
            self._tool_store.start_tool(
                thread_id=self.thread_id,
                run_id=run_id,
                name=tool_name,
                arguments=input_str,
                path=self.current_tool_path
            )

        # Emit structured stream event
        await self._publish_stream_event(StreamEvent(
            type=StreamEventType.TOOL_START.value,
            message=friendly_name,
            data={"tool": tool_name, "params": data}
        ))

        logger.info(f"[Tool Start] {tool_name}")

        # Handle special tool types
        if self.thread_id:
            if tool_name == "task_boundary":
                try:
                    data = json.loads(input_str)
                    mode = data.get("Mode")
                    tname = data.get("TaskName")
                    tstatus = data.get("TaskStatus")
                    if mode and tname:
                        await self.monitor.update_agent_state(self.thread_id, mode, tname, tstatus)
                except Exception:
                    pass

            if is_state_mutating_tool(tool_name):
                try:
                    if input_str.strip().startswith("{"):
                        data = json.loads(input_str)
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
                except Exception:
                    pass

            if metadata.get("is_memory_tool"):
                try:
                    data = json.loads(input_str) if input_str.strip().startswith("{") else {}
                    action = data.get("action", "")
                    key = data.get("key") or data.get("query") or data.get("name") or "Unknown"
                    memory_name = f"{action or tool_name}: {key[:30]}"
                    await self.monitor.set_active_memory(self.thread_id, f"tool-{tool_name}", memory_name)
                except Exception:
                    pass

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Run when tool ends running."""
        if self.thread_id and self.tool_task_id:
            await self.monitor.update_step(self.thread_id, self.tool_task_id, "done")
            self.tool_task_id = None

        # Get tool state from shared store
        run_id = str(kwargs.get("run_id", "default"))
        tool_state = None
        if self.thread_id:
            tool_state = self._tool_store.end_tool(self.thread_id, run_id)

        # Generate result summary using shared logic
        tool_name = self.current_tool_name
        
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

        logger.info(f"[Tool End] {tool_name}")

        # Emit structured stream event
        if tool_name:
            await self._publish_stream_event(StreamEvent(
                type=StreamEventType.TOOL_COMPLETE.value,
                message=log_output_str[:200],
                data={"tool": tool_name, "duration": duration, "success": True}
            ))

    async def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when tool errors."""
        logger.error(f"Tool Error in thread {self.thread_id}: {error}")
        
        if self.thread_id and self.tool_task_id and self.monitor:
            exc_name = type(error).__name__
            if "Interrupt" in exc_name or "GraphInterrupt" in exc_name:
                await self.monitor.update_step(self.thread_id, self.tool_task_id, "done")
            else:
                await self.monitor.update_step(self.thread_id, self.tool_task_id, "failed", details=str(error))
            
            self.tool_task_id = None

        # Emit structured stream event
        tool_name = getattr(self, 'current_tool_name', None)
        if tool_name:
            await self._publish_stream_event(StreamEvent(
                type=StreamEventType.TOOL_ERROR.value,
                message=str(error)[:200],
                data={"tool": tool_name, "success": False}
            ))

    async def on_chain_start(self, serialized: dict[str, Any], inputs: dict[str, Any], **kwargs: Any) -> None:
        """Run when chain (node) starts running."""
        metadata = kwargs.get("metadata", {})
        node_name = metadata.get("langgraph_node")

        if node_name and self.thread_id and self.monitor:
            standard_node_names = {
                "supervisor": "Supervisor Phase",
                "finish": "Completion Phase",
                "chat": "Interaction Phase",
                "flash_brain": "Cognitive Awakening",
            }

            phase_name = standard_node_names.get(node_name)
            
            if node_name == "worker" or not phase_name:
                execution_ticket = inputs.get("execution_ticket") or {}
                agent_config = execution_ticket.get("agent_config") or {}
                role_name = agent_config.get("role_name")
                
                if role_name:
                    phase_name = f"{role_name} Phase"
                else:
                    phase_name = f"{node_name.replace('_', ' ').title()} Phase"

            friendly_name = f"► {phase_name}"
            ignorable_nodes = ("__start__", "__end__", "language_router")
            
            if node_name not in ignorable_nodes:
                run_id = kwargs.get("run_id")
                task_id = await self.monitor.add_step(self.thread_id, friendly_name, "node")
                self._active_nodes[run_id] = (task_id, node_name)
                self._current_phase_task_id = task_id

    async def on_chain_end(self, outputs: dict[str, Any], **kwargs: Any) -> None:
        """Run when chain ends running."""
        run_id = kwargs.get("run_id")
        if run_id in self._active_nodes:
            task_id, node_name = self._active_nodes[run_id]
            if self.thread_id and self.monitor:
                await self.monitor.update_step(self.thread_id, task_id, "done")
                if getattr(self, "_current_phase_task_id", None) == task_id:
                    self._current_phase_task_id = None
            del self._active_nodes[run_id]

    async def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when chain errors."""
        run_id = kwargs.get("run_id")
        if run_id in self._active_nodes:
            task_id, node_name = self._active_nodes[run_id]
            if self.thread_id and self.monitor:
                exc_name = type(error).__name__
                if "Interrupt" in exc_name or "GraphInterrupt" in exc_name:
                    await self.monitor.update_step(self.thread_id, task_id, "done")
                else:
                    await self.monitor.update_step(self.thread_id, task_id, "failed", details=str(error))
            del self._active_nodes[run_id]

    async def on_text(self, text: str, **kwargs: Any) -> None:
        """Run on arbitrary text."""
        logger.info(f"[Text] {text}")
