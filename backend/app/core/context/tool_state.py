"""
Tool execution state management for the context module.

Provides centralized tool state tracking per thread to avoid duplication
across multiple callback handlers.

Usage:
    from app.core.context import tool_state_store, ToolState
    
    # In callback handler
    state = tool_state_store.start_tool(thread_id, run_id, tool_name, args)
    ...
    state = tool_state_store.end_tool(thread_id, run_id)
    if state:
        summary, is_file = state.get_summary(output)
"""

import time
from typing import Optional, Any

from pydantic import BaseModel, Field

from app.core.tools.registry import get_tool_metadata
from app.i18n.service import i18n
from app.utils.model_helpers import LegacyDictMixin

logger = __import__("logging").getLogger(__name__)


class ToolState(BaseModel, LegacyDictMixin):
    """
    Immutable state for a single tool execution.
    
    This model holds all information needed to track a tool's
    lifecycle and generate summaries for various outputs.
    """
    name: str
    arguments: str
    start_time: float
    path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_summary(self, output: str) -> tuple[str, bool]:
        """
        Generate summary for tool output.
        
        Centralizes the summary logic that was previously duplicated
        across TransparentCallbackHandler and EvoCloudCallbackHandler.
        
        Args:
            output: Raw tool output
            
        Returns:
            tuple: (processed_output, is_file_content)
            - processed_output: Summary or truncated output
            - is_file_content: Whether tool affects file paths
        """
        # Check if tool affects file paths (for UI display)
        affected_keys = self.metadata.get("affected_path_keys", [])
        is_file_content = len(affected_keys) > 0
        
        # Try to use result summary template from metadata
        summary_template = self.metadata.get("result_summary_template")
        
        # Ensure output is string for processing
        output_str = str(output) if not isinstance(output, str) else output
        
        if summary_template and output:
            try:
                line_count = len(output_str.splitlines())
                file_info = self.path or "file"
                return (
                    i18n.get(summary_template, path=file_info, count=line_count, 
                            lines=line_count, items=line_count),
                    is_file_content
                )
            except Exception:
                pass
        
        # Truncate if output is too long (>500 chars or >20 lines)
        if len(output_str) > 500:
            lines = output_str.splitlines()
            if len(lines) > 20:
                return (
                    f"{output_str[:300]}\n...\n[Truncated {len(lines)} lines / {len(output_str)} chars]",
                    is_file_content
                )
        
        return output_str, is_file_content


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

    def start_tool(self, thread_id: str, run_id: str, name: str, 
                   arguments: str, path: str | None = None) -> ToolState:
        """
        Record the start of a tool execution.
        
        Args:
            thread_id: The thread/session ID
            run_id: The LangChain run_id for this tool execution
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
            metadata=metadata
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
            run_id: The LangChain run_id for this tool execution
            
        Returns:
            ToolState if found, None otherwise
        """
        with self._store_lock:
            thread_tools = self._tools.get(thread_id)
            if thread_tools:
                return thread_tools.pop(run_id, None)
            return None

    def get_tool(self, thread_id: str, run_id: str) -> ToolState | None:
        """
        Get current state for a tool execution.
        
        Args:
            thread_id: The thread/session ID
            run_id: The LangChain run_id for this tool execution
            
        Returns:
            ToolState if found, None otherwise
        """
        with self._store_lock:
            thread_tools = self._tools.get(thread_id)
            if thread_tools:
                return thread_tools.get(run_id)
            return None

    def get_duration(self, thread_id: str, run_id: str) -> float | None:
        """
        Get elapsed time for a running tool.
        
        Args:
            thread_id: The thread/session ID
            run_id: The LangChain run_id for this tool execution
            
        Returns:
            Duration in seconds if tool is running, None otherwise
        """
        state = self.get_tool(thread_id, run_id)
        if state:
            return round(time.time() - state.start_time, 2)
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

    def clear_all(self):
        """Clear all tool states. Use with caution."""
        with self._store_lock:
            self._tools.clear()
            logger.info("Cleared all tool states")


# Global singleton instance
tool_state_store = ToolStateStore()
