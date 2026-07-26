"""Background agent execution loop."""

import logging
import time
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager, EvoContext
from app.core.context.thread_store import thread_context_store
from app.core.engine.background_agent.errors import handle_task_exception
from app.core.engine.background_agent.models import BackgroundAgentInputs
from app.core.engine.callbacks.database_logger import DatabaseCallbackHandler
from app.core.engine.callbacks.transparent import TransparentCallbackHandler
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException, InferenceError
from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger(__name__)

MAX_GOAL_LENGTH = 500


async def run_agent_background(thread_id: str, inputs: BackgroundAgentInputs | dict[str, Any]):
    """Background task executing nodes via the native agent loop."""
    if isinstance(inputs, dict):
        inputs = BackgroundAgentInputs(**inputs)

    project_id = inputs.project_id
    if project_id is None:
        project_id = DEFAULT_PROJECT_ID

    task_type = inputs.metadata.get("task_type") if inputs.metadata else None
    db_callback = None
    try:
        async with activity_monitor.run_scope(
            thread_id, inputs.goal, task_type=task_type, project_id=project_id
        ) as run_id:
            try:
                loaded_ctx = await ContextManager.load(thread_id)

                ctx = loaded_ctx
                working_dir = inputs.working_directory
                if not working_dir:
                    working_dir = thread_context_store.get_working_directory(thread_id)

                if not ctx:
                    ctx = EvoContext(
                        thread_id=thread_id,
                        project_id=project_id,
                        working_directory=working_dir,
                        active_model=inputs.model,
                        command_id=inputs.command_id,
                    )
                else:
                    ctx.request_id = f"bg-{thread_id}-{int(time.time())}"
                    ctx.working_directory = working_dir
                    ctx.command_id = inputs.command_id
                    ctx.active_model = inputs.model or ctx.active_model

                if not ctx.member_id and inputs.metadata.get("member_id"):
                    try:
                        ctx.member_id = int(inputs.metadata["member_id"])
                    except (ValueError, TypeError):
                        pass

                ctx.metadata.source = inputs.metadata.get("source", "")

                ContextManager.set(ctx)

                ctx = ContextManager.current()
                working_dir = ctx.working_directory

                config: dict[str, Any] = {
                    "configurable": {
                        "thread_id": thread_id,
                        "working_directory": working_dir,
                        "run_id": run_id,
                        "model": inputs.model,
                    },
                    "metadata": {
                        "project_id": project_id,
                        "is_retry": inputs.is_retry,
                        **inputs.metadata,
                    },
                }

                # Two-tier LLM: when lightning mode is active, Supervisor uses the
                # local fast model, Worker/Finish keep the default model.
                from app.infrastructure.config.service import SystemConfigService
                lightning_mode = SystemConfigService.get_value("LIGHTNING_MODE", "none")
                lightning_base = SystemConfigService.get_value("LIGHTNING_BASE_URL", "")
                if lightning_mode not in ("none", ""):
                    lightning_model = SystemConfigService.get_value("LIGHTNING_LLM_MODEL", "")
                    lightning_ctx = SystemConfigService.get_value("LIGHTNING_CTX", "8192")
                    if lightning_model:
                        config["configurable"]["lightning_model"] = lightning_model
                        config["configurable"]["lightning_base_url"] = lightning_base
                        config["configurable"]["lightning_api_key"] = SystemConfigService.get_value("LIGHTNING_API_KEY", "")
                        config["configurable"]["lightning_ctx"] = lightning_ctx
                        config["configurable"]["worker_model"] = inputs.model

                callback = TransparentCallbackHandler(thread_id=thread_id)
                db_callback = DatabaseCallbackHandler(
                    thread_id=thread_id,
                    project_id=project_id,
                    run_id=run_id,
                    member_id=ctx.member_id or 0,
                )
                config["configurable"]["message_handler"] = db_callback._handler

                from app.core.engine.message.converter import EvoMessageConverter
                from app.core.engine.state import AgentState

                raw_data = inputs.model_dump(exclude={"blackboard"})
                current_messages = EvoMessageConverter.repair(raw_data.get("messages", []))

                # Load historical messages from DB for multi-turn context
                try:
                    from app.infrastructure.database import session_scope
                    from app.models import Message as MessageModel
                    from sqlalchemy import select
                    from app.core.engine.message.converter import EvoMessageConverter
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
                                        d["additional_kwargs"] = {
                                            "thinking": m.thinking,
                                            "reasoning_content": m.thinking,
                                        }
                                    if getattr(m, "tool_calls", None):
                                        d["tool_calls"] = m.tool_calls
                                elif m.role == "tool":
                                    d["role"] = "tool"
                                    d["tool_call_id"] = m.tool_call_id
                                    d["name"] = m.tool_name
                                history_dicts.append(d)
                            if history_dicts:
                                history = EvoMessageConverter.repair(history_dicts)
                                current_messages = history + current_messages
                                logger.info("loaded %d history msgs for thread %s", len(history_dicts), thread_id)
                except Exception as e:
                    logger.debug("history load skipped: %s", e)

                raw_data["messages"] = current_messages
                agent_state = AgentState.model_validate(raw_data)
                last_human_msg = inputs.session_goal or ""

                from app.core.engine.context_hydrator import AgentContextHydrator

                lc_config = {
                    "configurable": config["configurable"],
                    "metadata": config["metadata"],
                }

                await AgentContextHydrator.hydrate(
                    ctx=ctx,
                    state=agent_state,
                    config=lc_config,
                    last_human_msg=last_human_msg,
                    is_retry=inputs.is_retry,
                    is_subtask=False,
                    iteration_count=inputs.iteration_count,
                )

                if inputs.hitl_resume_response:
                    from app.core.hitl.orchestrator import HITLOrchestrator
                    pending_tool = await HITLOrchestrator.get_pending_request(thread_id, inputs.model)
                    if pending_tool:
                        logger.info(f"[Resume] Auto-completing tool call {pending_tool['name']} on resume")
                        normalized_input = await HITLOrchestrator.handle_resume(
                            thread_id, pending_tool, inputs.hitl_resume_response
                        )
                        from app.core.engine.message.repository import MessageRepository
                        repo = MessageRepository(thread_id, project_id, member_id=ctx.member_id)
                        await repo.persist(
                            role="tool",
                            content=normalized_input,
                            tool_call_id=pending_tool["id"],
                            tool_name=pending_tool["name"],
                            category="tool",
                            action_type="tool_response",
                            status="completed",
                        )

                callbacks = [callback]
                if db_callback:
                    callbacks.append(db_callback)

                # Imitation-learning trace capture (chain A): persist agent
                # tool calls / results into trace_events so record_episode_task
                # and skill synthesis have raw material.
                from app.core.learning.trace_recorder import TraceCallbackHandler

                callbacks.append(TraceCallbackHandler(thread_id=thread_id, run_id=run_id))
                config["callbacks"] = callbacks

                agent_state.next_node = inputs.metadata.get("initial_node", "supervisor")
                agent_state.session_goal = inputs.session_goal or inputs.goal

                from app.core.engine.loop import run_node_loop

                await run_node_loop(agent_state, config, thread_id, log_prefix="BackgroundAgent")

                await ContextManager.save(thread_id)

            except AgentCancelledException:
                return
            except AgentHumanInterruptException:
                raise
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, InferenceError) as e:
                handler = db_callback._handler if db_callback else None
                await handle_task_exception(thread_id, project_id, e, handler=handler)
                # Always publish AgentRunCompletedEvent regardless of terminal flag,
                # so VoiceChannel can push voice.route_result {failed} to the HUD.
                from app.core.engine.event.publishers import publish_agent_run_completed
                await publish_agent_run_completed(
                    thread_id=thread_id,
                    project_id=project_id,
                    status="failed",
                    source=inputs.metadata.get("source", ""),
                    payload={"summary": str(e)[:300]},
                )
                return
    except AgentHumanInterruptException:
        return
