"""The single EvoLoop ↔ OpenHands Conversation execution bridge."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.engine.message.native_classes import BaseMessage
from app.core.engine.react.prompts import build_system_prompt
from app.core.engine.sdk_adapter import conversations
from app.core.engine.sdk_adapter.events import SDKEventBridge
from app.core.engine.sdk_adapter.llm import create_sdk_llm
from app.core.engine.sdk_adapter.reset import reset_conversation_store
from app.core.engine.sdk_adapter.tools import build_sdk_tools
from app.core.engine.state import AgentState
from app.core.exceptions import AgentCancelledException

logger = logging.getLogger(__name__)


def _conversation_id(thread_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(thread_id)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"evoloop:{thread_id}")


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "\n".join(
        str(item.get("text") or item.get("content") or item)
        if isinstance(item, dict)
        else str(item)
        for item in content
    )


def _latest_human_message(state: AgentState) -> str:
    for message in reversed(state.messages or []):
        if message.role in ("human", "user"):
            return _message_text(message)
    return state.session_goal or ""


def _sdk_message_event(message: BaseMessage):
    from openhands.sdk.event import MessageEvent
    from openhands.sdk.llm import Message, MessageToolCall, TextContent

    content = _message_text(message)
    role = "assistant" if message.role in ("ai", "assistant") else message.role
    if role == "human":
        role = "user"
    if role not in ("user", "assistant", "tool"):
        return None

    calls = []
    for call in message.tool_calls or []:
        if hasattr(call, "model_dump"):
            call = call.model_dump(mode="json")
        if isinstance(call, dict):
            arguments = call.get("arguments") or call.get("args") or {}
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            calls.append(
                MessageToolCall(
                    id=str(call.get("id") or "evoloop-tool-call"),
                    name=str(call.get("name") or "unknown"),
                    arguments=arguments,
                    origin="completion",
                )
            )

    llm_message = Message(
        role=role,
        content=[TextContent(text=content)],
        tool_calls=calls,
        tool_call_id=message.tool_call_id,
        name=message.name,
    )
    source = (
        "agent" if role == "assistant" else "user" if role == "user" else "environment"
    )
    return MessageEvent(source=source, llm_message=llm_message)


def _replay_state_history(
    conversation: Any, state: AgentState, bridge: Any
) -> None:
    """Seed a fresh SDK EventLog from the existing DB-backed AgentState."""

    conversation._ensure_agent_ready()
    if len(conversation.state.events) > 1:
        return

    last_human_index = -1
    for index, message in enumerate(state.messages or []):
        if message.role in ("human", "user"):
            last_human_index = index
    if last_human_index < 0:
        return

    bridge.replaying = True
    try:
        for message in state.messages[:last_human_index]:
            event = _sdk_message_event(message)
            if event is not None:
                conversation._on_event(event)
    finally:
        bridge.replaying = False


def _synthesize_dangling_action_observation(conversation: Any) -> None:
    """Complete a dangling ActionEvent left by an in-tool suspend + restart.

    The tool waiter dies with the process; a persisted ActionEvent without a
    matching ObservationEvent would break the next provider call. Synthetic
    error feedback keeps the LLM history valid (same contract as SDK's own
    interrupt path `_emit_orphaned_action_errors`).
    """

    from openhands.sdk.event import ActionEvent, AgentErrorEvent, ObservationEvent

    events = conversation.state.events
    if len(events) == 0:
        return

    last_action = None
    last_observation = None
    for event in reversed(events):
        if last_observation is None and isinstance(event, ObservationEvent):
            last_observation = event
        if last_action is None and isinstance(event, ActionEvent):
            last_action = event
        if last_action is not None and last_observation is not None:
            break

    if last_action is None:
        return
    if last_observation is not None:
        action_index = events.get_index(last_action.id)
        observation_index = events.get_index(last_observation.id)
        if observation_index > action_index:
            return

    conversation._on_event(
        AgentErrorEvent(
            error=(
                "该工具调用在等待人工确认或服务重启期间被中断，未取得执行结果。"
                "请根据当前任务状态重试该操作或继续任务。"
            ),
            tool_name=last_action.tool_name,
            tool_call_id=last_action.tool_call_id,
        )
    )
    logger.warning(
        "[SDKBridge] synthesized missing observation for dangling action %s",
        last_action.tool_call_id,
    )


async def _ask_human_on_stuck(thread_id: str, state: AgentState) -> str:
    """StuckDetector 触发后的产品语义：问人"停止/继续"（对齐 legacy doom guard）。

    - 非 docker：创建 choice 请求 → 推送 → 抛 AgentHumanInterruptException，
      session 层挂起等答复；答复"继续"后重建 state 重跑（SDK send_message
      会把 STUCK 重置为 IDLE）。
    - docker（hitl_enabled=False）：raise_hitl_interrupt 豁免不抛，返回
      "stop" 走确定性收尾。
    - 问询自身失败（DB 不可用等）：降级确定性收尾，不阻断值守。
    """

    from app.core.exceptions import AgentHumanInterruptException
    from app.core.hitl.core import (
        create_request,
        push_hitl_notification,
        raise_hitl_interrupt,
    )

    try:
        request = await create_request(
            thread_id=thread_id,
            request_type="choice",
            prompt=(
                "检测到 Agent 连续重复无进展（卡死检测）。"
                "为避免空转，是否停止本轮？"
            ),
            options=["停止", "继续"],
            default_value="停止",
        )
        await push_hitl_notification(
            thread_id=thread_id,
            request=request,
            request_data={
                "id": request.id,
                "type": "choice",
                "prompt": request.prompt,
                "options": ["停止", "继续"],
                "default_value": "停止",
            },
            project_id=state.project_id,
            tool_name="stuck_detector",
        )
        raise_hitl_interrupt(request.id, "StuckDetector: 请选择停止或继续")
    except AgentHumanInterruptException:
        raise
    except Exception:
        logger.warning(
            "[SDKBridge] stuck ask failed; fallback deterministic stop",
            exc_info=True,
        )
        return "stop"
    return "stop"


def _build_conversation(
    *,
    llm: Any,
    tools: list[Any],
    system_prompt: str,
    working_directory: str,
    persistence_dir: Path,
    thread_id: str,
    max_steps: int,
    bridge: SDKEventBridge,
):
    from openhands.sdk import Agent, Conversation

    return Conversation(
        agent=Agent(
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            # SDK 默认附加 finish/think 元工具；evoloop 的结束语义是
            # "无 tool_calls 的文本回复即终止"，finish 会提前吃掉收尾并
            # 绕过 evoloop 消息契约，因此工具面严格等于包装器产物。
            include_default_tools=[],
            tool_concurrency_limit=8,
            # 上下文压缩：EventLog 无限增长会撞模型 context window（legacy
            # ContextTrimmer 已删，压缩职责由 SDK condenser 承担——整合时
            # 漏配，长对话必炸，见 settings.SDK_CONDENSER_* 注释）。
            condenser=_build_condenser(llm),
        ),
        workspace=working_directory,
        persistence_dir=persistence_dir,
        conversation_id=_conversation_id(thread_id),
        callbacks=[bridge],
        token_callbacks=[bridge.on_token],
        max_iteration_per_run=max_steps,
        visualizer=None,
        delete_on_close=False,
    )


def _build_condenser(llm: Any) -> Any:
    """按 settings 构建摘要压缩器；max_size<=0 表示禁用（返回 None）。"""
    from openhands.sdk.context.condenser import LLMSummarizingCondenser

    max_size = settings.SDK_CONDENSER_MAX_SIZE
    if max_size <= 0:
        logger.info("[SDKBridge] condenser disabled (SDK_CONDENSER_MAX_SIZE<=0)")
        return None
    # SDK 校验：max_size//2 - keep_first - 1 必须为正（压缩后尾部保留空间）。
    keep_first = min(settings.SDK_CONDENSER_KEEP_FIRST, max(0, max_size // 2 - 2))
    logger.info(
        "[SDKBridge] condenser configured: LLMSummarizingCondenser(max_size=%d, keep_first=%d)",
        max_size,
        keep_first,
    )
    return LLMSummarizingCondenser(
        llm=llm,
        max_size=max_size,
        keep_first=max(0, keep_first),
    )


async def run_turn(
    *,
    state: AgentState,
    config: dict[str, Any],
    thread_id: str,
    max_steps: int | None = None,
    log_prefix: str = "SDKAgent",
    steer_provider: Any | None = None,
) -> dict[str, Any]:
    """Run one delivery through OpenHands while preserving EvoLoop boundaries.

    The Conversation is cached per thread (see ``conversations.py``): rebuilding
    it per delivery would re-read the whole EventLog from disk every turn. Tool
    face additions mid-delivery go through the packages_dirty watcher; LLM is
    switched only when the auth token changed.
    """

    logger.info("[%s] starting OpenHands SDK turn", log_prefix)
    loop = asyncio.get_running_loop()
    ctx = ContextManager.current()
    conversation_id = str(_conversation_id(thread_id))
    tool_history: list[str] = []
    system_prompt = await build_system_prompt(state, config)
    user_message = _latest_human_message(state)
    persistence_dir = Path(settings.APP_DATA_DIR) / "sdk-conversations"
    working_directory = ctx.working_directory or os.getcwd()
    effective_max_steps = max_steps or settings.AGENT_MAX_STEPS
    token = ctx.token or ""

    bridge = SDKEventBridge(config=config, thread_id=thread_id)
    await bridge.start_llm_callbacks()

    cached = conversations.get_cached(thread_id)
    if cached is not None:
        conversation = cached.conversation
        # Capability face may have changed since last delivery: add new tools.
        tools = await build_sdk_tools(
            state,
            config,
            loop=loop,
            tool_history=tool_history,
            conversation_id=conversation_id,
        )
        existing = set(conversation.agent.tools_map)
        added = []
        for spec in tools:
            if spec.name in existing:
                continue
            from openhands.sdk.tool.registry import resolve_tool

            added.extend(resolve_tool(spec, conversation.state))
            existing.add(spec.name)
        if added:
            conversation.agent.add_runtime_tools(added)
            logger.info(
                "[%s] added %d tools on cached conversation", log_prefix, len(added)
            )
        if token != cached.last_token:
            llm = await create_sdk_llm(ctx, config)
            try:
                conversation.llm_registry.remove(llm.usage_id)
            except KeyError:
                pass
            conversation.switch_llm(llm)
            cached.last_token = token
            logger.info("[%s] switched LLM after token refresh", log_prefix)
    else:
        # Cache miss (process restart / eviction): stale persisted state on
        # disk would resume with deserialized non-client tool defs that
        # collide with the freshly registered ClientTools ("collides with an
        # existing non-client tool"). The DB replay below is the authoritative
        # history, so drop the SDK store and rebuild from scratch.
        removed = await asyncio.to_thread(reset_conversation_store, thread_id)
        if removed:
            logger.info(
                "[%s] dropped stale SDK store for %s (cache miss rebuild)",
                log_prefix,
                thread_id,
            )
        tools = await build_sdk_tools(
            state,
            config,
            loop=loop,
            tool_history=tool_history,
            conversation_id=conversation_id,
        )
        llm = await create_sdk_llm(ctx, config)
        conversation = _build_conversation(
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            working_directory=working_directory,
            persistence_dir=persistence_dir,
            thread_id=thread_id,
            max_steps=effective_max_steps,
            bridge=bridge,
        )
        _replay_state_history(conversation, state, bridge)
        _synthesize_dangling_action_observation(conversation)
        conversations.put_cached(
            thread_id,
            conversations.CachedConversation(
                conversation=conversation,
                tool_names={spec.name for spec in tools},
                last_token=token,
            ),
        )

    if user_message:
        conversation.send_message(user_message)

    cancel_error: list[BaseException] = []
    watchers_stop = asyncio.Event()

    async def _watch_cancellation() -> None:
        """Poll the DB stop flag every 2s until the run finishes.

        Each probe runs as its OWN task and is never cancelled: hard-cancelling
        a probe mid-``session_scope.__aexit__`` leaves the aiosqlite connection
        unreturned (GC "non-checked-in connection" leak). Shutdown only flips
        ``watchers_stop``; the in-flight probe finishes and closes cleanly.
        """

        from app.core.monitoring.activity import activity_monitor

        while not watchers_stop.is_set():
            probe = asyncio.create_task(
                activity_monitor.check_cancellation(thread_id)
            )
            done, _pending = await asyncio.wait(
                {probe}, timeout=2.0, return_when=asyncio.FIRST_EXCEPTION
            )
            if probe in done:
                try:
                    await probe
                except AgentCancelledException as exc:
                    cancel_error.append(exc)
                    conversation.interrupt()
                    return
                except asyncio.CancelledError:
                    return
            # Timed-out probes keep running to completion on their own so the
            # DB session closes normally; a stale probe result is harmless
            # (the next probe re-reads the flag).

    async def _watch_steer() -> None:
        if steer_provider is None:
            return
        while True:
            try:
                messages = await steer_provider()
            except AgentCancelledException as exc:
                # legacy steer_provider raises on session_cancel while draining
                # the gate; the watcher must turn it into an interrupt or the
                # SDK run would keep going after a stop request.
                cancel_error.append(exc)
                conversation.interrupt()
                return
            except Exception:
                logger.warning(
                    "[%s] steer_provider failed", log_prefix, exc_info=True
                )
                await asyncio.sleep(0.2)
                continue
            for message in messages:
                await asyncio.to_thread(
                    conversation.send_message,
                    _message_text(message),
                )
            await asyncio.sleep(0.2)

    async def _watch_runtime_tools() -> None:
        from openhands.sdk.tool.registry import resolve_tool

        while True:
            await asyncio.sleep(0.2)
            if not getattr(ctx.metadata, "packages_dirty", False):
                continue
            ctx.metadata.packages_dirty = False
            try:
                refreshed_specs = await build_sdk_tools(
                    state,
                    config,
                    loop=loop,
                    tool_history=tool_history,
                    conversation_id=conversation_id,
                )
                existing = set(conversation.agent.tools_map)
                added = []
                for spec in refreshed_specs:
                    if spec.name in existing:
                        continue
                    added.extend(resolve_tool(spec, conversation.state))
                if added:
                    conversation.agent.add_runtime_tools(added)
                    logger.info(
                        "[%s] added %d SDK tools after capability activation",
                        log_prefix,
                        len(added),
                    )
            except Exception:
                logger.exception(
                    "[%s] SDK runtime tool rebind failed", log_prefix
                )

    watchers = [asyncio.create_task(_watch_cancellation())]
    if steer_provider is not None:
        watchers.append(asyncio.create_task(_watch_steer()))
    watchers.append(asyncio.create_task(_watch_runtime_tools()))
    failure: BaseException | None = None
    try:
        await conversation.arun()
        if cancel_error:
            raise cancel_error[0]
        await bridge.flush()
    except Exception as exc:
        failure = exc
    finally:
        # Graceful watcher shutdown: flip the stop event first (the
        # cancellation watcher's DB probe is never hard-cancelled — see its
        # docstring), then cancel the DB-free watchers and wait them out.
        watchers_stop.set()
        for watcher in watchers:
            if watcher is not watchers[0]:
                watcher.cancel()
        await asyncio.gather(*watchers, return_exceptions=True)

    if failure is not None:
        should_retry = await _handle_run_failure(
            failure,
            attempt=1,
            log_prefix=log_prefix,
        )
        if should_retry:
            # AUTH retry: refresh the token on the same cached conversation.
            llm = await create_sdk_llm(ctx, config)
            try:
                conversation.llm_registry.remove(llm.usage_id)
            except KeyError:
                pass
            conversation.switch_llm(llm)
            await conversation.arun()
            await bridge.flush()

    status = str(getattr(conversation.state.execution_status, "value", ""))
    error_events = [event for event in bridge.events if getattr(event, "code", "")]
    is_truncated = status == "error" and any(
        "maximum" in str(getattr(event, "detail", "")).lower()
        or getattr(event, "code", "") == "MaxIterationsReached"
        for event in error_events
    )
    if status == "paused":
        raise AgentCancelledException("OpenHands conversation interrupted")
    if status == "stuck":
        await _ask_human_on_stuck(thread_id, state)
        return _deterministic_stop(tool_history)
    if status == "error" and not is_truncated:
        from app.core.engine.sdk_adapter import SDKAdapterError

        detail = str(error_events[-1]) if error_events else "unknown SDK error"
        raise SDKAdapterError(detail)
    if is_truncated:
        from app.core.engine.message.publisher import MessagePublisher
        from app.models.schemas.events import MaxStepsReachedEvent

        await MessagePublisher(thread_id=thread_id).publish(
            MaxStepsReachedEvent(
                thread_id=thread_id,
                message=(
                    f"本轮执行达到 SDK iteration 上限（{effective_max_steps} 步），"
                    "将在此处暂告一段落。"
                ),
            )
        )
    # SDK 路径的 state.messages 不承载会话消息（内核是 EventLog），legacy
    # _record_metrics 按 state.messages 计数恒为 0（2026-09-25 实测观测盲区
    # ：llm_calls/tokens 全 0，配额燃烧率与单轮成本不可见）。llm_calls 在
    # 此从 EventLog 补记——LLM 轮次 = ActionEvent（产出工具调用的响应）+
    # assistant MessageEvent（收尾回复）。（2026-09-25 校准：HN 轮 store 实
    # 测 22 ActionEvent + 1 assistant MessageEvent = 23 轮，仅数 MessageEvent
    # 会低估 20 倍）。
    # tokens 依赖 litellm usage（目前进 LLMCompletionLogEvent 的文件日志，
    # EventLog 内不可得），留待专门的日志解析接线。
    llm_metrics: dict[str, int] | None = None
    try:
        llm_metrics = {
            "llm_calls": sum(
                1
                for event in conversation.state.events
                if (getattr(event, "kind", "") or getattr(event, "type", ""))
                == "ActionEvent"
                or (
                    getattr(event, "llm_message", None) is not None
                    and getattr(event.llm_message, "role", None) == "assistant"
                )
            ),
            "input_tokens": 0,
            "output_tokens": 0,
            "tool_errors": 0,
        }
    except Exception:
        logger.warning(
            "[%s] SDK llm metrics collection failed", log_prefix, exc_info=True
        )
    await _run_completion_pipeline(
        thread_id, ctx, config, state, bridge, log_prefix, llm_metrics=llm_metrics
    )
    return {
        "messages": [],
        "tool_history": tool_history,
        "is_truncated": is_truncated,
        "outcome": "truncated" if is_truncated else "success",
    }


def _deterministic_stop(tool_history: list[str]) -> dict[str, Any]:
    return {
        "messages": [],
        "tool_history": tool_history,
        "is_truncated": True,
        "outcome": "truncated",
    }


async def _handle_run_failure(
    failure: BaseException,
    *,
    attempt: int,
    log_prefix: str,
) -> bool:
    """Translate a raised SDK run failure. Returns True when caller must retry."""

    from openhands.sdk.conversation.exceptions import ConversationRunError

    if not isinstance(failure, ConversationRunError):
        raise failure

    classification = getattr(
        getattr(failure, "conversation_error", None), "classification", None
    )
    kind = str(getattr(classification, "kind", ""))

    if kind == "auth":
        if attempt == 1:
            logger.warning(
                "[%s] LLM auth failure; retrying once with refreshed token",
                log_prefix,
            )
            return True  # caller switches LLM (fresh token) and reruns
        from app.core.exceptions import InferenceError

        raise InferenceError(
            error_type="llm_auth",
            status_code=401,
            user_friendly_msg="LLM 认证失败（已重试仍失败），请重新登录后重试。",
            raw_error=str(failure),
        )
    if kind == "quota":
        from app.core.exceptions import InferenceError

        raise InferenceError(
            error_type="quota_exhausted",
            status_code=None,
            user_friendly_msg="LLM 配额/预算已耗尽。",
            raw_error=str(failure),
        )

    from app.core.engine.sdk_adapter import SDKAdapterError

    raise SDKAdapterError(str(failure))


async def _run_completion_pipeline(
    thread_id: str,
    ctx: Any,
    config: dict[str, Any],
    state: AgentState,
    bridge: SDKEventBridge,
    log_prefix: str,
    *,
    llm_metrics: dict[str, int] | None = None,
) -> None:
    try:
        from app.core.engine.react.completion import publish_session_completed_react

        await publish_session_completed_react(
            thread_id,
            ctx.project_id,
            config,
            state,
            summary=bridge.summary,
            run_id=getattr(ctx, "run_id", None) or config.get("configurable", {}).get("run_id"),
        )
    except Exception:
        logger.warning(
            "[%s] SDK completion pipeline failed", log_prefix, exc_info=True
        )
    if not llm_metrics:
        return
    try:
        from app.core.monitoring.activity_state import ActivityStateService

        await ActivityStateService().update_metrics(thread_id, **llm_metrics)
        logger.info(
            "[%s] SDK llm metrics recorded: %s",
            log_prefix,
            {k: llm_metrics[k] for k in sorted(llm_metrics)},
        )
    except Exception:
        logger.warning(
            "[%s] SDK llm metrics write failed", log_prefix, exc_info=True
        )
