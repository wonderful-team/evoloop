"""Background agent execution loop."""

import logging
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.engine.background_agent.errors import handle_task_exception
from app.core.engine.background_agent.models import BackgroundAgentInputs
from app.core.exceptions import (
    AgentCancelledException,
    AgentHumanInterruptException,
)
from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger(__name__)

MAX_GOAL_LENGTH = 500


async def run_agent_background(thread_id: str, inputs: BackgroundAgentInputs | dict[str, Any]):
    """Background task executing nodes via the native agent loop.

    单发（subagent/Autonomous Task/代码生成）入口。config/state/callbacks
    构建统一复用 ``app.core.engine.runner_base``（与 session 路径共享，
    消除两套执行路径的重复实现）。
    """
    if isinstance(inputs, dict):
        inputs = BackgroundAgentInputs(**inputs)

    project_id = inputs.project_id
    if project_id is None:
        project_id = DEFAULT_PROJECT_ID

    task_type = inputs.metadata.get("task_type") if inputs.metadata else None
    try:
        async with activity_monitor.run_scope(
            thread_id, inputs.goal, task_type=task_type, project_id=project_id
        ) as run_id:
            try:
                from app.core.engine.runner_base import (
                    build_agent_state,
                    build_ctx,
                    build_execution_config,
                )

                ctx = await build_ctx(thread_id, inputs, run_id=run_id)
                config = build_execution_config(thread_id, project_id, inputs, run_id, ctx)
                agent_state = await build_agent_state(thread_id, inputs)

                from app.core.engine.context_hydrator import AgentContextHydrator

                lc_config = {
                    "configurable": config["configurable"],
                    "metadata": config["metadata"],
                }
                await AgentContextHydrator.hydrate(
                    ctx=ctx,
                    state=agent_state,
                    config=lc_config,
                    last_human_msg=inputs.session_goal or "",
                    is_retry=inputs.is_retry,
                    iteration_count=inputs.iteration_count,
                )

                if inputs.hitl_resume_response:
                    from app.core.hitl.orchestrator import HITLOrchestrator

                    # 统一恢复路径：关闭请求 + 审批重执行 + 持久化工具结果
                    await HITLOrchestrator.resume_and_persist(
                        thread_id=thread_id,
                        project_id=project_id,
                        member_id=ctx.member_id,
                        config=config,
                        user_input=inputs.hitl_resume_response,
                        state=agent_state,
                    )

                agent_state.next_node = inputs.metadata.get("initial_node", "supervisor")
                agent_state.session_goal = inputs.session_goal or inputs.goal

                from app.core.engine.loop import run_node_loop

                await run_node_loop(agent_state, config, thread_id, log_prefix="BackgroundAgent")

                await ContextManager.save(thread_id)

            except AgentCancelledException:
                return
            except AgentHumanInterruptException:
                raise
            except Exception as e:
                handler = None
                if "config" in locals():
                    handler = config.get("configurable", {}).get("message_handler")
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
