from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from pydantic import BaseModel

from app.core.engine.hooks import HookContext, HookEvent, ToolResult, hook_system
from app.core.engine.hooks.schemas import ToolInput
from app.core.engine.message.native_classes import BaseMessage, ToolMessage
from app.core.engine.state import AgentState, RunnableConfigMetadata
from app.core.exceptions import AgentHumanInterruptException
from app.core.tools import get_working_directory
from app.utils.extract import safe_parse_json
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)

#: 会话已用工具记录上限（防 metadata 无限增长；超出后不再记，保底面封顶）
USED_NATIVE_TOOLS_CAP = 50


def record_used_native_tool(metadata: Any, tool_name: str) -> None:
    """向 ctx.metadata.used_native_tools 追加已执行工具（append-only 去重）。"""
    try:
        used = getattr(metadata, "used_native_tools", None)
        if used is None or tool_name in used or len(used) >= USED_NATIVE_TOOLS_CAP:
            return
        used.append(tool_name)
    except Exception:
        logger.exception(
            "[ToolExecutor] failed to record used native tool '%s'", tool_name
        )


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
            tool_args = safe_parse_json(tool_args) or {}
        if not isinstance(tool_args, dict):
            tool_args = {}

        meta = RunnableConfigMetadata.from_config(self.config)
        thread_id = meta.thread_id
        member_id = meta.member_id
        project_id = meta.project_id
        run_id = meta.run_id

        logger.info(
            f"[{self.name}] 🛠   Call: {tool_name} | Args: {json.dumps(tool_args)}"
        )

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
            pre_result = await hook_system.trigger(
                HookEvent.PRE_TOOL_USE, pre_ctx, blocking=True
            )

            if pre_result.block:
                logger.warning(
                    f"[{self.name}] 🚫 Tool {tool_name} blocked by hook: {pre_result.message}"
                )
                msg = self._create_tool_message(
                    content=f"Error: Tool execution blocked - {pre_result.message}",
                    tool_id=tool_id,
                    tool_name=tool_name,
                    run_id=run_id,
                )
                return ToolExecutionResult(message=msg)

            if (
                pre_result.modified_context
                and pre_result.modified_context.tool_input is not None
            ):
                tool_input = pre_result.modified_context.tool_input
                # Full-roundtrip write-back: the vault placeholder hook now substitutes
                # across all fields (declared + dynamic extra), so we must persist every
                # non-None field back into tool_args — not just the 5 legacy fields
                # (command/path/content/query/args). Otherwise run_macro `params` and
                # browser_control action fields would be replaced in the hook but lost here.
                dumped = tool_input.model_dump()
                tool_args = {k: v for k, v in dumped.items() if v is not None}

            tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
            async with self._history_lock:
                local_tool_history.append(tool_sig)
            # 会话已用工具记账（工具面收窄的保险下限）：通过 PRE_TOOL_USE 钩子
            # 放行即算"用过"，被拦截的不算。mcp__ 工具也记（保底层在静态面内
            # 查不到即无操作，MCP 可用性由 loaded_packages 持久保证）。
            record_used_native_tool(ctx.metadata, tool_name)

            is_mutating = tool.metadata.get("is_state_mutating", False)
            if self.enable_diff_tracking and is_mutating:
                from app.core.file.changes.tracker import file_change_tracker
                from app.core.tools.registry import get_tool_affected_paths

                snapshot_paths = get_tool_affected_paths(tool_name, tool_args)
                resolved_abs_paths = []
                for path in snapshot_paths:
                    try:
                        abs_path = path
                        if not os.path.isabs(abs_path):
                            wd = get_working_directory(self.config)
                            abs_path = os.path.abspath(os.path.join(wd, abs_path))

                        resolved_abs_paths.append(abs_path)
                        if not file_change_tracker.has_snapshot(abs_path, thread_id):
                            file_change_tracker.capture(abs_path, thread_id)
                            logger.info(
                                f"[{self.name}] Captured snapshot for: {abs_path}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"[ToolExecutor] Failed to resolve path for snapshot: {path} | Error: {e}",
                            exc_info=True,
                        )

                self._current_resolved_paths = resolved_abs_paths

            config = {**(self.config or {})}
            # ctx.messages 透传（对齐 OpenCode tool Context.messages）：工具可通过
            # config.configurable._messages 读取当前完整消息流（历史只读）。
            config["configurable"] = {
                **(config.get("configurable") or {}),
                "_messages": self.state.messages or [],
            }

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
                await emit_tool_start(
                    tool_callbacks,
                    tool_name,
                    tool_args,
                    tool_run_id,
                    tool_call_id=tool_id,
                )

            content = await self._tool_executor.execute(tool, tool_args, config=config)

            if tool_callbacks:
                await emit_tool_end(
                    tool_callbacks, tool_name, str(content), tool_run_id
                )

            post_ctx = HookContext(
                thread_id=thread_id,
                member_id=member_id,
                project_id=project_id,
                tool_name=tool_name,
                tool_input=ToolInput.model_validate(tool_args),
                tool_result=ToolResult(output=content),
                tool_use_id=tool_id,
                state=self.state,
                extra=pre_result.modified_context.extra
                if (pre_result and pre_result.modified_context)
                else pre_ctx.extra,
            )
            try:
                post_result = await hook_system.trigger(
                    HookEvent.POST_TOOL_USE, post_ctx, blocking=True
                )
                if (
                    post_result
                    and post_result.modified_context
                    and post_result.modified_context.tool_result
                ):
                    content = post_result.modified_context.tool_result.output
            except Exception as hook_err:
                logger.warning(
                    f"[ToolExecutor] POST_TOOL_USE hook failed: {hook_err}",
                    exc_info=True,
                )

            tool_message_id = gen_uuid()

            # A.0 统一截断：超限工具输出自动折叠 + 落盘 + outputPath 回填
            # （OpenCode truncate 语义，工具作者无感知；react 模式默认开启）。
            content_str = str(content)
            attachments: list[dict] = []
            raw = content
            if isinstance(raw, dict) and raw.get("attachments"):
                raw_attach = raw.get("attachments")
                if isinstance(raw_attach, list):
                    attachments = [a for a in raw_attach if isinstance(a, dict)]

            # A.0 统一截断：超限工具输出自动折叠 + 落盘 + outputPath 回填
            # （OpenCode truncate 语义，工具作者无感知；单 Agent ReAct 下始终启用）。
            from app.core.engine.react.truncate import truncate_output

            t = truncate_output(content_str, thread_id=thread_id)
            if t.truncated:
                content_str = t.content
            content = content_str

            if self.enable_diff_tracking and tool.metadata.get("is_state_mutating"):
                await self._track_diffs(
                    tool_name, tool_args, thread_id, tool_message_id, tool_id, tool
                )

            msg = self._create_tool_message(
                content=str(content),
                tool_id=tool_id,
                tool_name=tool_name,
                run_id=run_id,
                message_id=tool_message_id,
                attachments=attachments or None,
            )
            return ToolExecutionResult(message=msg, raw_result=content)

        except AgentHumanInterruptException:
            # HITL 中断：清理本次捕获的快照，避免内存泄漏 / 陈旧快照被复用。
            self._discard_snapshots(thread_id)
            raise
        except Exception as e:
            content = f"Error executing {tool_name}: {e}"

            # 工具执行失败：快照不会被 _track_diffs 消费，必须丢弃。
            self._discard_snapshots(thread_id)

            # 审计修复：PRE_TOOL_USE 钩子等在回调变量赋值前抛异常时，
            # 此处直接引用会 UnboundLocalError 掩盖原始错误。
            tool_callbacks = locals().get("tool_callbacks")
            tool_run_id = locals().get("tool_run_id", "")
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
                extra=pre_result.modified_context.extra
                if (
                    "pre_result" in locals()
                    and pre_result
                    and pre_result.modified_context
                )
                else pre_ctx.extra,
            )

            async def _fire_fail_hook():
                try:
                    await hook_system.trigger(HookEvent.POST_TOOL_USE_FAILURE, fail_ctx)
                except Exception as hook_err:
                    logger.warning(
                        f"[ToolExecutor] POST_TOOL_USE_FAILURE hook failed: {hook_err}",
                        exc_info=True,
                    )

            asyncio.create_task(_fire_fail_hook())

            msg = self._create_tool_message(
                content=content,
                tool_id=tool_id,
                tool_name=tool_name,
                run_id=run_id,
            )
            return ToolExecutionResult(message=msg, raw_result=None)

    def _discard_snapshots(self, thread_id: str) -> None:
        """丢弃本次调用已捕获但未消费的快照（执行失败 / HITL 中断路径）。"""
        from app.core.file.changes.tracker import file_change_tracker

        for path in getattr(self, "_current_resolved_paths", None) or []:
            file_change_tracker.discard(path, thread_id)
        self._current_resolved_paths = []

    async def _track_diffs(
        self,
        tool_name: str,
        tool_args: dict,
        thread_id: str,
        message_id: str,
        tool_call_id: str,
        tool: Any = None,
    ) -> None:
        from app.core.file.changes.tracker import file_change_tracker

        # 调用点已按 is_state_mutating 门控并传入工具对象，此处仅做防御性校验
        # （不再重复 get_tool_map 全局查找）。
        if not tool or not tool.metadata.get("is_state_mutating"):
            return

        snapshot_paths = self._current_resolved_paths
        if not snapshot_paths:
            return

        meta = RunnableConfigMetadata.from_config(self.config)
        for path in snapshot_paths:
            try:
                await file_change_tracker.compute_and_persist(
                    path=path,
                    thread_id=thread_id,
                    message_id=str(message_id),
                    tool_call_id=tool_call_id,
                    run_id=meta.run_id,
                )
            except OSError as e:
                logger.exception(f"Failed to process diff for {path}: {e}")

    async def execute_batch(
        self,
        tool_calls: list[dict],
        local_tool_history: list[str],
        parallel: bool = False,
    ) -> list[BaseMessage]:
        async def _run_one(tc: dict) -> BaseMessage:
            result = await self.execute_tool(
                tool_name=tc["name"],
                tool_args=tc["args"],
                tool_id=tc["id"],
                local_tool_history=local_tool_history,
            )
            return result.message

        if parallel:
            return list(await asyncio.gather(*[_run_one(tc) for tc in tool_calls]))

        results: list[BaseMessage] = []
        for tc in tool_calls:
            results.append(await _run_one(tc))
        return results

    def _create_tool_message(
        self,
        content: str,
        tool_id: str,
        tool_name: str,
        run_id: str | None,
        message_id: str | None = None,
        attachments: list[dict] | None = None,
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
            attachments=attachments or [],
        )
