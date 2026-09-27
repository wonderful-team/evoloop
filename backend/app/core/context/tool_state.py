"""Tool execution state management for the context module.

Provides centralized tool state tracking per thread to avoid duplication
across multiple callback handlers.

Usage:
    from app.core.context import tool_state_store, ToolState

    # In callback handler
    state = tool_state_store.start_tool(thread_id, run_id, tool_name, args)
    ...
    state = tool_state_store.end_tool(thread_id, run_id)
    if state:
        summary = state.get_summary(output)
"""

import logging
import time
from threading import Lock
from typing import Any

from pydantic import Field

from app.core.tools.registry import get_tool_metadata
from app.i18n.service import i18n
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class ToolState(DynamicBaseModel):
    """
    Immutable state for a single tool execution.

    This model holds all information needed to track a tool's
    lifecycle and generate summaries for various outputs.
    """

    name: str
    arguments: str
    start_time: float
    path: str | None = None
    metadata: Any = Field(default_factory=dict)

    def get_summary(self, output: str) -> str:
        """
        Generate summary for tool output.

        Centralizes the summary logic that was previously duplicated
        across TransparentCallbackHandler and EvoCloudCallbackHandler.

        Args:
            output: Raw tool output

        Returns:
            Summary text（走 summary_template，过长时截断）。
            注：不再从 ``affected_path_keys`` 推导 "is_file_content"——那是
            UI 展示语义，与快照路径契约无关（UI 改由 tool_meta.affected_paths
            提供实际受影响路径）。本方法当前无生产调用者，仅作工具摘要格式化。
        """
        # Try to use summary template from metadata
        summary_template = self.metadata.get("summary_template")

        # Ensure output is string for processing
        output_str = str(output) if not isinstance(output, str) else output

        if summary_template and output:
            try:
                line_count = len(output_str.splitlines())
                file_info = self.path or "file"
                return i18n.get(
                    summary_template,
                    path=file_info,
                    count=line_count,
                    lines=line_count,
                    items=line_count,
                )
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        # Truncate if output is too long (>500 chars or >20 lines)
        if len(output_str) > 500:
            lines = output_str.splitlines()
            if len(lines) > 20:
                return f"{output_str[:300]}\n...\n[Truncated {len(lines)} lines / {len(output_str)} chars]"

        return output_str


class ToolStateStore:
    """
    Thread-safe store for managing tool execution states.

    This is a singleton that maintains tool state per thread_id,
    similar to ThreadContextStore. It allows multiple callback
    handlers to share tool information without duplication.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        # Mapping: thread_id -> {run_id -> ToolState}
        self._tools: dict[str, dict[str, ToolState]] = {}
        self._store_lock = Lock()

    def start_tool(
        self,
        thread_id: str,
        run_id: str,
        name: str,
        arguments: str,
        path: str | None = None,
    ) -> ToolState:
        """
        Record the start of a tool execution.

        Args:
            thread_id: The thread/session ID
            run_id: The run_id for this tool execution
            name: Tool name
            arguments: JSON string of tool arguments
            path: Optional affected file path

        Returns:
            ToolState: The created state object
        """
        metadata = get_tool_metadata(name) or {}
        state = ToolState(
            name=name,
            arguments=arguments,
            start_time=time.time(),
            path=path,
            metadata=metadata,
        )

        with self._store_lock:
            if thread_id not in self._tools:
                self._tools[thread_id] = {}
            self._tools[thread_id][run_id] = state

        return state

    def end_tool(self, thread_id: str, run_id: str) -> ToolState | None:
        """
        Record the end of a tool execution and return its state.

        Args:
            thread_id: The thread/session ID
            run_id: The run_id for this tool execution

        Returns:
            ToolState if found, None otherwise
        """
        with self._store_lock:
            thread_tools = self._tools.get(thread_id)
            if thread_tools:
                return thread_tools.pop(run_id, None)
            return None

    def clear_thread(self, thread_id: str):
        """
        Clear all tool states for a thread.
        Should be called when thread completes or to clean up.

        Args:
            thread_id: The thread/session ID to clear
        """
        with self._store_lock:
            if thread_id in self._tools:
                del self._tools[thread_id]
                logger.debug(f"Cleared tool states for thread {thread_id}")


# Global singleton instance
tool_state_store = ToolStateStore()
