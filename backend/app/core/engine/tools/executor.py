"""
Shared tool execution logic for AgentEngine.

Consolidates duplicate code from _execute_react_loop and _execute_single_shot.
"""

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from app.core.engine.hooks import HookContext, HookEvent, ToolResult, hook_system
from app.core.engine.state import AgentState, RunnableConfigMetadata
from app.infrastructure.queue.factory import get_scheduler
from app.utils.diff import diff_tracker
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class ToolExecutionResult(BaseModel):
    """Result of a tool execution, including the message and raw output."""
    message: ToolMessage
    raw_result: Any | None = None


class AgentToolExecutor:
    """
    Executes tools with hooks, diff tracking, and error handling.

    Consolidates common logic from:
    - _execute_react_loop._process_single_tool
    - _execute_single_shot._execute_tool
    """

    def __init__(
        self,
        tool_map: dict[str, Any],
        state: AgentState,
        config: dict,
        name: str = "Agent",
        enable_diff_tracking: bool = True,
    ):
        from app.core.engine.state import ensure_state
        from app.core.tools.executor import ToolExecutor
        self.tool_map = tool_map
        self.state = ensure_state(state)
        self.config = config
        self.name = name
        self.enable_diff_tracking = enable_diff_tracking
        self._tool_executor = ToolExecutor()
        self._history_lock = asyncio.Lock()  # Lock for thread-safe local_tool_history access

    async def execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_id: str,
        local_tool_history: list[str],
    ) -> ToolExecutionResult:
        """
        Execute a single tool with full lifecycle management.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Tool arguments
            tool_id: Unique tool call ID
            local_tool_history: List to track tool signatures for repetition detection

        Returns:
            ToolMessage with execution result
        """
        meta = RunnableConfigMetadata.from_config(self.config)
        thread_id = meta.thread_id
        user_id = meta.user_id
        project_id = meta.project_id
        run_id = meta.run_id

        logger.info(f"[{self.name}] 🛠️ Call: {tool_name} | Args: {json.dumps(tool_args)}")

        tool = self.tool_map.get(tool_name)
        if not tool:
            msg = self._create_tool_message(
                content=f"Error: Tool {tool_name} not found.",
                tool_id=tool_id,
                tool_name=tool_name,
                run_id=run_id,
            )
            return ToolExecutionResult(message=msg)

        try:
            # === HOOK: PreToolUse ===
            pre_ctx = HookContext(
                thread_id=thread_id,
                user_id=user_id,
                project_id=project_id,
                tool_name=tool_name,
                tool_input=tool_args,
                tool_use_id=tool_id,
                blackboard=self.state.blackboard,
            )
            pre_result = await hook_system.trigger(HookEvent.PRE_TOOL_USE, pre_ctx, blocking=True)

            if pre_result.block:
                logger.warning(f"[{self.name}] 🚫 Tool {tool_name} blocked by hook: {pre_result.message}")
                msg = self._create_tool_message(
                    content=f"Error: Tool execution blocked - {pre_result.message}",
                    tool_id=tool_id,
                    tool_name=tool_name,
                    run_id=run_id,
                )
                return ToolExecutionResult(message=msg)

            # Update context if modified
            if pre_result.modified_context and pre_result.modified_context.tool_input is not None:
                tool_input = pre_result.modified_context.tool_input
                tool_args = tool_input.args if tool_input.args else tool_args

            # Track tool execution history and detect repetitions (thread-safe)
            tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
            async with self._history_lock:
                if tool_sig in local_tool_history:
                    logger.warning(f"[{self.name}] ⚠️ REPETITION DETECTED: Agent is repeating tool call: {tool_sig}")
                local_tool_history.append(tool_sig)

            # Execute Tool
            content = await self._tool_executor.execute(tool, tool_args, config=self.config)

            # === HOOK: PostToolUse ===
            post_ctx = HookContext(
                thread_id=thread_id,
                user_id=user_id,
                project_id=project_id,
                tool_name=tool_name,
                tool_input=tool_args,
                tool_result=ToolResult(output=content),
                tool_use_id=tool_id,
                blackboard=self.state.blackboard,
            )
            # Fire-and-forget hook with error handling wrapper
            async def _fire_hook():
                try:
                    await hook_system.trigger(HookEvent.POST_TOOL_USE, post_ctx)
                except Exception as hook_err:
                    logger.warning(f"[ToolExecutor] POST_TOOL_USE hook failed: {hook_err}")

            asyncio.create_task(_fire_hook())

            # Diff Tracking (if enabled)
            if self.enable_diff_tracking:
                await self._track_diffs(tool_name, tool_args, thread_id, tool_id)

            msg = self._create_tool_message(
                content=str(content),
                tool_id=tool_id,
                tool_name=tool_name,
                run_id=run_id,
            )
            return ToolExecutionResult(message=msg, raw_result=content)

        except Exception as e:
            content = f"Error executing {tool_name}: {e}"

            # === HOOK: PostToolUseFailure ===
            fail_ctx = HookContext(
                thread_id=thread_id,
                user_id=user_id,
                project_id=project_id,
                tool_name=tool_name,
                tool_input=tool_args,
                tool_use_id=tool_id,
                error=e,
                error_message=str(e),
                blackboard=self.state.blackboard,
            )
            # Fire-and-forget hook with error handling wrapper
            async def _fire_fail_hook():
                try:
                    await hook_system.trigger(HookEvent.POST_TOOL_USE_FAILURE, fail_ctx)
                except Exception as hook_err:
                    logger.warning(f"[ToolExecutor] POST_TOOL_USE_FAILURE hook failed: {hook_err}")

            asyncio.create_task(_fire_fail_hook())

            msg = self._create_tool_message(
                content=content,
                tool_id=tool_id,
                tool_name=tool_name,
                run_id=run_id,
            )
            return ToolExecutionResult(message=msg, raw_result=None)

    async def _track_diffs(
        self,
        tool_name: str,
        tool_args: dict,
        thread_id: str,
        tool_id: str,
    ) -> None:
        """Track file diffs after tool execution."""
        from app.core.tools.registry import get_tool_affected_paths

        snapshot_paths = get_tool_affected_paths(tool_name, tool_args)

        # Capture Snapshots
        for path in snapshot_paths:
            diff_tracker.capture_snapshot(path, thread_id)

        # Compute and persist diffs
        for path in snapshot_paths:
            try:
                operation, diff, original_content = diff_tracker.compute_diff(path, thread_id)
                if diff:
                    logger.info(f"📝 Diff Detected ({operation}) on {path} (Persisting in Background)")
                    try:
                        from app.core.engine.state.config import RunnableConfigMetadata
                        meta = RunnableConfigMetadata.from_config(self.config)
                        msg_id = meta.run_id or tool_id
                        get_scheduler().send_task(
                            "engine_persist_file_operation",
                            kwargs={
                                "thread_id": thread_id,
                                "message_id": str(msg_id),
                                "file_path": path,
                                "operation": operation,
                                "diff_content": diff,
                                "original_content": original_content,
                            }
                        )
                    except Exception:
                        logger.warning("Failed to dispatch FileOperation to Celery.")
            except Exception as e:
                logger.error(f"Failed to process diff for {path}: {e}")

    def _create_tool_message(
        self,
        content: str,
        tool_id: str,
        tool_name: str,
        run_id: str | None,
    ) -> ToolMessage:
        """Create a ToolMessage with run_id metadata."""
        metadata = {"run_id": run_id} if run_id else {}

        return ToolMessage(
            content=str(content),
            tool_call_id=tool_id,
            name=tool_name,
            id=gen_uuid(),
            metadata=metadata,
            additional_kwargs=metadata,
        )
