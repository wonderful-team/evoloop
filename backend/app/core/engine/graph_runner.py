"""Graph execution runner for background resumption (native lightweight implementation)."""

import logging

from app.constants import DEFAULT_PROJECT_ID
from app.core.engine.callbacks.database_logger import DatabaseCallbackHandler
from app.core.engine.callbacks.transparent import TransparentCallbackHandler
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException
from app.core.monitoring.activity import activity_monitor

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
    from app.core.engine.state import AgentState
    from app.core.engine.message.converter import EvoMessageConverter

    await ContextManager.load(thread_id)

    if isinstance(inputs, dict) and "messages" in inputs:
        inputs["messages"] = EvoMessageConverter.repair(inputs["messages"])
    state = AgentState.model_validate(inputs)
    state.next_node = "supervisor"

    callback = TransparentCallbackHandler(thread_id=thread_id)
    raw_project_id = config.get("metadata", {}).get("project_id") if config else None
    project_id = int(raw_project_id) if raw_project_id is not None else DEFAULT_PROJECT_ID
    run_id = config.get("configurable", {}).get("run_id", f"resume-{thread_id}") if config else f"resume-{thread_id}"

    db_callback = DatabaseCallbackHandler(
        thread_id=thread_id,
        project_id=project_id,
        run_id=run_id,
    )

    try:
        if clear_human_request_flag:
            await activity_monitor.clear_human_request(thread_id)

        await activity_monitor.start_run(thread_id, run_label)

        resume_config = {**config, "callbacks": [callback, db_callback]}

        from app.core.engine.loop import run_node_loop

        await run_node_loop(state, resume_config, thread_id, log_prefix="ResumeGraph")

        await ContextManager.save(thread_id)
        await activity_monitor.end_run(thread_id, "done")

    except AgentCancelledException:
        await activity_monitor.end_run(thread_id, "cancelled")
    except AgentHumanInterruptException:
        logger.info(f"Resume interrupted for human input: {thread_id}")
        await activity_monitor.end_run(thread_id, "human_interrupt")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Resume error for {thread_id}: {e}")
        await activity_monitor.end_run(thread_id, "failed")
