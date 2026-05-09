"""
Graph execution runner for background resumption.

Wraps ``graph.astream()`` with activity-monitor lifecycle and
standard exception handling.
"""

import logging

from app.core.engine.callbacks.database_logger import DatabaseCallbackHandler
from app.core.engine.callbacks.transparent import TransparentCallbackHandler
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException
from app.core.globals import get_graph
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
    """
    Unified background graph resumption loop.

    Used by ``/chat/resume`` and ``/hitl/cancel``.
    """
    graph = get_graph()
    if not graph:
        logger.error(f"[Dispatch] Cannot resume {thread_id}: graph not initialized")
        await activity_monitor.end_run(thread_id, "failed")
        return

    callback = TransparentCallbackHandler(thread_id=thread_id)

    # Extract project_id from config metadata (same pattern as run_agent_background)
    project_id = int(config.get("metadata", {}).get("project_id"))
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

        async for _event in graph.astream(inputs, config=resume_config):
            await activity_monitor.check_cancellation(thread_id)

        await activity_monitor.end_run(thread_id, "done")

    except AgentCancelledException:
        await activity_monitor.end_run(thread_id, "cancelled")
    except AgentHumanInterruptException:
        logger.info(f"Resume interrupted for human input: {thread_id}")
        await activity_monitor.end_run(thread_id, "human_interrupt")
    except Exception as e:
        logger.error(f"Resume error for {thread_id}: {e}")
        await activity_monitor.end_run(thread_id, "failed")
