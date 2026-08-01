from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.core.engine.hooks import HookContext, HookEvent, ToolResult, hook_system
from app.core.engine.hooks.schemas import ToolInput
from app.core.engine.message.native_classes import BaseMessage, ToolMessage
from app.core.engine.signals import AgentSignal, signal_manager
from app.core.engine.state import AgentState, RunnableConfigMetadata
from app.core.exceptions import AgentHumanInterruptException
from app.core.tools import get_working_directory
from app.infrastructure.queue.factory import get_scheduler
from app.utils.diff import diff_tracker
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class ToolExecutionResult(BaseModel):
    """Result of a tool execution, including the message and raw output."""
    model_config = {"arbitrary_types_allowed": True}

    message: BaseMessage
    raw_result: Any | None = None


class AgentToolExecutor:
    """
    Executes tools with hooks, diff tracking, and error handling.
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
        self._history_lock = asyncio.Lock()
        self._current_resolved_paths: list[str] = []

    async def execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_id: str,
        local_tool_history: list[str],
    ) -> ToolExecutionResult:
        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args) if tool_args.strip() else {}
            except (json.JSONDecodeError, ValueError):
                tool_args = {}
        if not isinstance(tool_args, dict):
            tool_args = {}

        meta = RunnableConfigMetadata.from_config(self.config)
        thread_id = meta.thread_id
        member_id = meta.member_id
        project_id = meta.project_id
        run_id = meta.run_id

        logger.info(f"[{self.name}] 🛠   Call: {tool_name} | Args: {json.dumps(tool_args)}")

        from app.core.context.manager import ContextManager
        ctx = ContextManager.current()
        if run_id and ctx.run_id != run_id:
            ctx.run_id = run_id

        tool = self.tool_map.get(tool_name)
        if not tool:
            msg = self._create_tool_message(
                content=f"Error: Tool {tool_name} not found.",
                tool_id=tool_id,
                tool_name=tool_name,
                run_id=run_id,
            )
            return ToolExecutionResult(message=msg)

        pre_ctx = HookContext(
            thread_id=thread_id,
            member_id=member_id,
            project_id=project_id,
            tool_name=tool_name,
            tool_input=ToolInput.model_validate(tool_args),
            tool_use_id=tool_id,
            state=self.state,
        )

        try:
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

            if pre_result.modified_context and pre_result.modified_context.tool_input is not None:
                tool_input = pre_result.modified_context.tool_input
                if tool_input.args:
                    tool_args = tool_input.args
                else:
                    for field, val in [
                        ("command", tool_input.command),
                        ("path", tool_input.path),
                        ("content", tool_input.content),
                        ("query", tool_input.query),
                    ]:
                        if val is not None and field in tool_args:
                            tool_args[field] = val

            tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
            async with self._history_lock:
                local_tool_history.append(tool_sig)

            is_mutating = tool.metadata.get("is_state_mutating", False)
            if self.enable_diff_tracking and is_mutating:
                from app.core.tools.registry import get_tool_affected_paths
                from app.utils.diff import diff_tracker

                snapshot_paths = get_tool_affected_paths(tool_name, tool_args)
                resolved_abs_paths = []
                for path in snapshot_paths:
                    try:
                        abs_path = path
                        if not os.path.isabs(abs_path):
                            wd = get_working_directory(self.config)
                            abs_path = os.path.abspath(os.path.join(wd, abs_path))

                        resolved_abs_paths.append(abs_path)
                        if not diff_tracker.has_snapshot(abs_path, thread_id):
                            diff_tracker.capture_snapshot(abs_path, thread_id)
                            logger.info(f"[{self.name}] Captured snapshot for: {abs_path}")
                    except Exception as e:
                        logger.warning(f"[ToolExecutor] Failed to resolve path for snapshot: {path} | Error: {e}")

                self._current_resolved_paths = resolved_abs_paths

            config = {**(self.config or {})}
            existing_metadata = config.get("metadata") or {}
            config["metadata"] = {**existing_metadata, "_evoloop_tool_call_id": tool_id}

            from uuid import uuid4 as _uuid4

            from app.core.engine.callbacks.bridge import (
                _get_callbacks,
                emit_tool_end,
                emit_tool_error,
                emit_tool_start,
            )
            tool_callbacks = _get_callbacks(self.config)
            tool_run_id = str(_uuid4())
            if tool_callbacks:
                await emit_tool_start(tool_callbacks, tool_name, tool_args, tool_run_id, tool_call_id=tool_id)

            content = await self._tool_executor.execute(tool, tool_args, config=config)

            if tool_callbacks:
                await emit_tool_end(tool_callbacks, tool_name, str(content), tool_run_id)

            post_ctx = HookContext(
                thread_id=thread_id,
                member_id=member_id,
                project_id=project_id,
                tool_name=tool_name,
                tool_input=ToolInput.model_validate(tool_args),
                tool_result=ToolResult(output=content),
                tool_use_id=tool_id,
                state=self.state,
                extra=pre_result.modified_context.extra if (pre_result and pre_result.modified_context) else pre_ctx.extra,
            )
            try:
                post_result = await hook_system.trigger(HookEvent.POST_TOOL_USE, post_ctx, blocking=True)
                if post_result and post_result.modified_context and post_result.modified_context.tool_result:
                    content = post_result.modified_context.tool_result.output
            except Exception as hook_err:
                logger.warning(f"[ToolExecutor] POST_TOOL_USE hook failed: {hook_err}")

            tool_message_id = gen_uuid()

            if self.enable_diff_tracking and tool.metadata.get("is_state_mutating"):
                await self._track_diffs(tool_name, tool_args, thread_id, tool_message_id, tool_id)

            msg = self._create_tool_message(
                content=str(content),
                tool_id=tool_id,
                tool_name=tool_name,
                run_id=run_id,
                message_id=tool_message_id,
            )
            return ToolExecutionResult(message=msg, raw_result=content)

        except AgentHumanInterruptException:
            raise
        except Exception as e:
            content = f"Error executing {tool_name}: {e}"

            if tool_callbacks:
                await emit_tool_error(tool_callbacks, tool_name, e, tool_run_id)

            fail_ctx = HookContext(
                thread_id=thread_id,
                member_id=member_id,
                project_id=project_id,
                tool_name=tool_name,
                tool_input=ToolInput.model_validate(tool_args),
                tool_use_id=tool_id,
                error=e,
                error_message=str(e),
                state=self.state,
                extra=pre_result.modified_context.extra if ('pre_result' in locals() and pre_result and pre_result.modified_context) else pre_ctx.extra,
            )
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
        message_id: str,
        tool_call_id: str,
    ) -> None:
        from app.core.tools.registry import get_tool_map

        tool_map = get_tool_map()
        tool_obj = tool_map.get(tool_name)

        if not tool_obj or not tool_obj.metadata.get("is_state_mutating"):
            return

        snapshot_paths = self._current_resolved_paths
        if not snapshot_paths:
            return

        for path in snapshot_paths:
            try:
                operation, diff, original_content = diff_tracker.compute_diff(path, thread_id)
                if diff:
                    logger.info(f"📝 Diff Detected ({operation}) on {path} (Persisting in Background)")
                    try:
                        from app.core.engine.state.config import RunnableConfigMetadata
                        meta = RunnableConfigMetadata.from_config(self.config)
                        msg_id = message_id
                        if settings.EMBEDDED_MODE:
                            from app.core.engine.tasks import (
                                _persist_file_operation_task,
                            )
                            await _persist_file_operation_task(
                                thread_id=thread_id,
                                message_id=str(msg_id),
                                file_path=path,
                                operation=operation,
                                diff_content=diff,
                                original_content=original_content,
                                run_id=meta.run_id,
                                tool_call_id=tool_call_id,
                            )
                        else:
                            get_scheduler().send_task(
                                "engine_persist_file_operation",
                                kwargs={
                                    "thread_id": thread_id,
                                    "message_id": str(msg_id),
                                    "file_path": path,
                                    "operation": operation,
                                    "diff_content": diff,
                                    "original_content": original_content,
                                    "run_id": meta.run_id,
                                    "tool_call_id": tool_call_id,
                                }
                            )
                    except Exception as e:
                        logger.warning(f"Failed to dispatch FileOperation to Celery: {e}")
            except OSError as e:
                logger.error(f"Failed to process diff for {path}: {e}")

    async def execute_batch(
        self,
        tool_calls: list[dict],
        local_tool_history: list[str],
        parallel: bool = False,
    ) -> tuple[list[BaseMessage], AgentSignal | None]:
        async def _run_one(tc: dict) -> tuple[BaseMessage, Any]:
            result = await self.execute_tool(
                tool_name=tc["name"],
                tool_args=tc["args"],
                tool_id=tc["id"],
                local_tool_history=local_tool_history,
            )
            return result.message, result.raw_result

        pending_signal = None
        results = []

        if parallel:
            batch_results = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
            for msg, raw in batch_results:
                results.append(msg)
                if not pending_signal:
                    tool_name = next(tc["name"] for tc in tool_calls if tc["id"] == msg.tool_call_id)
                    pending_signal = signal_manager.detect_post_execution_signal(tool_name, raw)
        else:
            for tc in tool_calls:
                msg, raw = await _run_one(tc)
                results.append(msg)
                if not pending_signal:
                    pending_signal = signal_manager.detect_post_execution_signal(tc["name"], raw)

        return results, pending_signal

    def _create_tool_message(
        self,
        content: str,
        tool_id: str,
        tool_name: str,
        run_id: str | None,
        message_id: str | None = None,
    ) -> BaseMessage:
        """Create a native tool message with run_id metadata."""
        metadata = {"run_id": run_id} if run_id else {}

        return ToolMessage(
            content=str(content),
            tool_call_id=tool_id,
            name=tool_name,
            id=message_id or gen_uuid(),
            metadata=metadata,
            additional_kwargs=metadata,
        )
