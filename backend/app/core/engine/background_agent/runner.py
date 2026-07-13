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


async def run_agent_background(
    thread_id: str, inputs: BackgroundAgentInputs | dict[str, Any]
):
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
                raw_data["messages"] = EvoMessageConverter.repair(raw_data.get("messages", []))
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

                agent_state.next_node = "supervisor"
                agent_state.session_goal = inputs.session_goal or inputs.goal

                from app.core.engine.loop import run_node_loop

                await run_node_loop(
                    agent_state, config, thread_id, log_prefix="BackgroundAgent"
                )

                await ContextManager.save(thread_id)

            except AgentCancelledException:
                return
            except AgentHumanInterruptException:
                raise
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, InferenceError) as e:
                handler = db_callback._handler if db_callback else None
                terminal = await handle_task_exception(thread_id, project_id, e, handler=handler)
                if not terminal:
                    from app.core.engine.event.publishers import publish_agent_run_completed
                    await publish_agent_run_completed(
                        thread_id=thread_id,
                        project_id=project_id,
                        status="failed",
                        payload={"summary": str(e)[:300]},
                    )
                return
    except AgentHumanInterruptException:
        return
