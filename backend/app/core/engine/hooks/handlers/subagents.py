"""
Subagent lifecycle hook handlers.
"""

import logging
from datetime import datetime

from app.core.engine.hooks.core import HookContext, HookResult

logger = logging.getLogger(__name__)


async def subagent_start_handler(context: HookContext) -> HookResult:
    """
    Track when subagents are spawned.

    Useful for:
    - Monitoring parallel execution
    - Resource tracking
    - Debugging multi-agent workflows
    """
    agent_id = context.metadata.get("agent_id", "unknown")
    agent_type = context.metadata.get("agent_type", "generic")
    parent_task = context.metadata.get("parent_task", "")

    logger.info(f"[SubagentStart] Spawned {agent_type} agent ({agent_id}) for: {parent_task[:50]}...")

    # Track in state
    active_agents = list(context.state.active_subagents or []) if context.state else []
    active_agents.append({
        "agent_id": agent_id,
        "agent_type": agent_type,
        "started_at": datetime.utcnow().isoformat(),
    })
    if context.state:
        context.state.active_subagents = active_agents

    return HookResult(
        success=True,
        data={"agent_id": agent_id, "active_count": len(active_agents)},
        modified_context=context,
    )


async def subagent_stop_handler(context: HookContext) -> HookResult:
    """
    Track when subagents complete.

    Useful for:
    - Collecting results
    - Cleanup
    - Coordination with parent
    """
    agent_id = context.metadata.get("agent_id", "unknown")
    outcome = context.metadata.get("outcome", "unknown")

    logger.info(f"[SubagentStop] Agent {agent_id} completed with outcome: {outcome}")

    # Update tracking
    active_agents = list(context.state.active_subagents or []) if context.state else []
    active_agents = [a for a in active_agents if a["agent_id"] != agent_id]
    if context.state:
        context.state.active_subagents = active_agents

    # Track completed
    completed = list(context.state.completed_subagents or []) if context.state else []
    completed.append({
        "agent_id": agent_id,
        "outcome": outcome,
        "completed_at": datetime.utcnow().isoformat(),
    })
    if context.state:
        context.state.completed_subagents = completed

    return HookResult(
        success=True,
        data={"agent_id": agent_id, "remaining": len(active_agents)},
        modified_context=context,
    )
