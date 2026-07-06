"""
Subtask spawning builder for parallel agent execution.

Consumes the spawn plan and routes to Worker.
"""

import logging

from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


def build_subtask_sends(state: AgentState) -> str:
    """
    Consume ``state.spawn_plan`` and route to Worker.

    Subtask configuration and parallel execution are handled by the
    Worker node using the existing ExecutionTicket from the Supervisor.
    """
    if state.spawn_plan and state.spawn_plan.subtasks:
        logger.info(f"[Router] Spawning {len(state.spawn_plan.subtasks)} parallel subtasks")
    state.spawn_plan = None
    return "worker"
