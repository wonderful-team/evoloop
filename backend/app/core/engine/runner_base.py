"""共享的 Agent 执行构建函数 — 单发（run_agent_background）与会话（run_agent_session）复用。

消除两套执行路径各自重复的 config/callback/state 构建：
- ``build_execution_config``：config + callbacks（lightning 两档模型、message_handler、trace）
- ``build_agent_state``：历史消息加载 + AgentState 构建
- ``build_ctx``：加载/构建 EvoContext
"""

from __future__ import annotations

import logging
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager, EvoContext
from app.core.context.thread_store import thread_context_store
from app.core.engine.background_agent.models import BackgroundAgentInputs
from app.core.engine.callbacks.database_logger import DatabaseCallbackHandler
from app.core.engine.callbacks.transparent import TransparentCallbackHandler
from app.core.engine.message.converter import EvoMessageConverter
from app.utils.id import unique_id

logger = logging.getLogger(__name__)


async def build_ctx(
    thread_id: str,
    inputs: BackgroundAgentInputs,
    run_id: str | None = None,
) -> EvoContext:
    """加载（或新建）thread 的 EvoContext，并用 inputs 刷新关键字段。"""
    loaded_ctx = await ContextManager.load(thread_id)
    project_id = inputs.project_id or DEFAULT_PROJECT_ID
    working_dir = inputs.working_directory or thread_context_store.get_working_directory(thread_id)

    if loaded_ctx is None:
        ctx = EvoContext(
            thread_id=thread_id,
            project_id=project_id,
            working_directory=working_dir,
            active_model=inputs.model,
            command_id=inputs.command_id,
            request_id=run_id or unique_id("bg", thread_id),
        )
    else:
        ctx = loaded_ctx
        ctx.request_id = run_id or unique_id("bg", thread_id)
        ctx.working_directory = working_dir
        ctx.command_id = inputs.command_id
        ctx.active_model = inputs.model or ctx.active_model
    if not ctx.project_id and project_id:
        ctx.project_id = project_id
    if not ctx.member_id and inputs.metadata and inputs.metadata.get("member_id"):
        try:
            ctx.member_id = int(inputs.metadata["member_id"])
        except (ValueError, TypeError):
            pass
    if inputs.metadata and inputs.metadata.get("source"):
        ctx.metadata.source = inputs.metadata["source"]
    ContextManager.set(ctx)
    return ctx


def build_callbacks(
    thread_id: str,
    project_id: int,
    run_id: str,
    member_id: int = 0,
) -> list[Any]:
    """组装标准 callbacks（transparent + database_logger）。"""
    callback = TransparentCallbackHandler(thread_id=thread_id)
    db_callback = DatabaseCallbackHandler(
        thread_id=thread_id,
        project_id=project_id,
        run_id=run_id,
        member_id=member_id,
    )
    return [callback, db_callback]


def build_execution_config(
    thread_id: str,
    project_id: int,
    inputs: BackgroundAgentInputs,
    run_id: str,
    ctx: EvoContext,
) -> dict[str, Any]:
    """构建执行 config + callbacks（与 session 路径完全一致）。"""
    working_dir = ctx.working_directory or ""
    model = inputs.model

    config: dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id,
            "working_directory": working_dir,
            "run_id": run_id,
            "model": model,
            # project_id/member_id 同时放 configurable（节点/工具从 configurable 读）
            # 与 metadata（会话/hydrator 从 metadata 读），保持两处一致。
            "project_id": ctx.project_id or project_id,
            "member_id": ctx.member_id or 0,
        },
        "metadata": {
            "project_id": project_id,
            "is_retry": inputs.is_retry,
            **inputs.metadata,
        },
    }

    # Two-tier LLM: Supervisor uses lightning (local), Worker/Finish keep default (cloud).
    from app.infrastructure.config.service import SystemConfigService

    lightning_mode = SystemConfigService.get_value("LIGHTNING_MODE", "none")
    if lightning_mode not in ("none", ""):
        lightning_model = SystemConfigService.get_value("LIGHTNING_LLM_MODEL", "")
        lightning_base = SystemConfigService.get_value("LIGHTNING_BASE_URL", "")
        lightning_ctx = SystemConfigService.get_value("LIGHTNING_CTX", "8192")
        if lightning_model:
            config["configurable"]["lightning_model"] = lightning_model
            config["configurable"]["lightning_base_url"] = lightning_base
            config["configurable"]["lightning_api_key"] = SystemConfigService.get_value("LIGHTNING_API_KEY", "")
            config["configurable"]["lightning_ctx"] = lightning_ctx
            config["configurable"]["worker_model"] = model

    callbacks = build_callbacks(thread_id, project_id, run_id, ctx.member_id or 0)
    config["configurable"]["message_handler"] = callbacks[1]._handler
    config["callbacks"] = callbacks
    return config


async def build_agent_state(
    thread_id: str,
    inputs: BackgroundAgentInputs,
) -> Any:
    """从 DB 历史 + 当前 inputs 构建 AgentState（多轮上下文）。"""
    from app.core.engine.state import AgentState as AgentStateModel

    current_messages = EvoMessageConverter.repair(inputs.messages or [])

    try:
        from sqlalchemy import select

        from app.infrastructure.database import session_scope
        from app.models import Message as MessageModel

        async with session_scope() as db:
            stmt = (
                select(MessageModel)
                .where(MessageModel.thread_id == thread_id)
                .order_by(MessageModel.sequence_number)
            )
            result = await db.execute(stmt)
            db_messages = result.scalars().all()
            if db_messages and len(db_messages) > len(current_messages):
                slice_idx = -len(current_messages) if len(current_messages) > 0 else None
                history_db_messages = db_messages[:slice_idx] if slice_idx is not None else db_messages
                history_dicts = []
                for m in history_db_messages:
                    d = {"role": m.role, "content": m.content or ""}
                    if m.role in ("human", "user"):
                        d["role"] = "user"
                    elif m.role in ("ai", "assistant"):
                        d["role"] = "assistant"
                        if getattr(m, "thinking", None):
                            d["additional_kwargs"] = {"thinking": m.thinking, "reasoning_content": m.thinking}
                        if getattr(m, "tool_calls", None):
                            d["tool_calls"] = m.tool_calls
                    elif m.role == "tool":
                        d["role"] = "tool"
                        d["tool_call_id"] = m.tool_call_id
                        d["name"] = m.tool_name
                    history_dicts.append(d)
                if history_dicts:
                    current_messages = EvoMessageConverter.repair(history_dicts) + current_messages
                logger.info("loaded %d history msgs for thread %s", len(history_dicts), thread_id)
    except Exception as e:
        logger.debug("history load skipped: %s", e)

    raw_data = inputs.model_dump(exclude={"blackboard"})
    raw_data["ticket"] = inputs.ticket
    raw_data["messages"] = current_messages
    state = AgentStateModel.model_validate(raw_data)
    state.thread_id = thread_id
    state.next_node = "supervisor"
    state.session_goal = inputs.session_goal or inputs.goal

    # Seed shared_context from the cached EvoContext so that flags written by
    # update_blackboard / report_outcome survive across user turns.
    ctx = ContextManager.current()
    if ctx and ctx.metadata and ctx.metadata.shared_context:
        cached = ctx.metadata.shared_context or {}
        if cached:
            state.shared_context = {**cached, **(state.shared_context or {})}
            logger.debug(
                "seeded state.shared_context from cached EvoContext for thread %s: keys=%s",
                thread_id,
                list(state.shared_context.keys()),
            )

    return state
