"""Graph execution runner for background resumption (native lightweight implementation)."""

import logging

from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.core.engine.state import AgentState
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException
from app.core.monitoring.activity import activity_monitor
from app.core.monitoring.constants import ActivityStatus
from app.infrastructure.database.sql.database import session_scope
from app.models import Message

logger = logging.getLogger(__name__)


async def resume_graph_background(
    thread_id: str,
    inputs: dict,
    config: dict,
    *,
    run_label: str = "Resuming...",
    clear_human_request_flag: bool = False,
):
    """Unified background execution resumption loop."""
    from app.core.context import ContextManager
    from app.core.engine.message.converter import EvoMessageConverter
    from app.core.engine.state import AgentState

    await ContextManager.load(thread_id)

    # Resume may be triggered from a background task where the cached context
    # did not retain the thread_id (or load failed). Make sure the current
    # context carries the thread_id before hydration uses it.
    ctx = ContextManager.current()
    if ctx.thread_id is None:
        ctx.thread_id = thread_id

    if isinstance(inputs, dict) and "messages" in inputs:
        inputs["messages"] = EvoMessageConverter.repair(inputs["messages"])
    state = AgentState.model_validate(inputs)
    state.next_node = "supervisor"

    # Restore context via hydration (skills index, telemetry, memory etc.)
    await _restore_resume_context(thread_id, state, config)

    raw_project_id = config.get("metadata", {}).get("project_id") if config else None
    project_id = (
        int(raw_project_id) if raw_project_id is not None else DEFAULT_PROJECT_ID
    )
    run_id = (
        config.get("configurable", {}).get("run_id", f"resume-{thread_id}")
        if config
        else f"resume-{thread_id}"
    )

    # 统一复用 runner_base.build_callbacks（与 session/单发路径一致）
    from app.core.engine.runner_base import build_callbacks

    callbacks = build_callbacks(thread_id, project_id, run_id)

    try:
        if clear_human_request_flag:
            await activity_monitor.clear_human_request(thread_id)

        await activity_monitor.start_run(
            thread_id, run_label, run_id=run_id, project_id=project_id
        )

        resume_config = {**config, "callbacks": callbacks}

        from app.core.engine.loop import run_node_loop

        await run_node_loop(state, resume_config, thread_id, log_prefix="ResumeGraph")

        await ContextManager.save(thread_id)
        await activity_monitor.end_run(thread_id, ActivityStatus.DONE, run_id=run_id)

    except AgentCancelledException:
        await activity_monitor.end_run(thread_id, ActivityStatus.CANCELLED, run_id=run_id)
    except AgentHumanInterruptException:
        logger.info(f"Resume interrupted for human input: {thread_id}", exc_info=True)
        await activity_monitor.end_run(
            thread_id, ActivityStatus.HUMAN_INTERRUPT, run_id=run_id
        )
    except Exception as e:
        logger.exception(f"Resume error for {thread_id}: {e}")
        await activity_monitor.end_run(thread_id, ActivityStatus.FAILED, run_id=run_id)


async def _restore_resume_context(
    thread_id: str, state: AgentState, config: dict
) -> None:
    """Restore context (skills, telemetry, memory) for a resumed agent session.

    During resume the AgentState is created fresh from the resume ToolMessage
    only, so AgentContextHydrator.hydrate needs to be called again to populate
    ctx.metadata.active_skills, environment telemetry, etc.
    """
    from app.core.context import ContextManager
    from app.core.engine.context_hydrator import AgentContextHydrator

    last_human_msg = ""
    try:
        async with session_scope() as session:
            stmt = (
                select(Message.content)
                .where(
                    Message.thread_id == thread_id,
                    Message.role == "human",
                    Message.name != "context_ticket",
                )
                .order_by(Message.sequence_number.desc())
                .limit(1)
            )
            res = await session.execute(stmt)
            row = res.scalar_one_or_none()
            if row:
                last_human_msg = str(row)[:500]
    except Exception:
        logger.warning("[ResumeGraph] Failed to load last human msg for hydration")

    ctx = ContextManager.current()
    await AgentContextHydrator.hydrate(
        ctx=ctx,
        state=state,
        config=config,
        last_human_msg=last_human_msg,
        is_retry=False,
        iteration_count=0,
    )
