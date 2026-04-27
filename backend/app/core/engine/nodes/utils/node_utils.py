"""
Shared utilities for EvoLoop engine nodes.

Extracts cross-cutting concerns (logging, state resolution, signal dispatch)
to eliminate duplication across BaseAgentNode, FinishNode, AggregatorNode, etc.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def resolve_is_subtask(state: Any) -> bool:
    """
    Robustly resolve `is_subtask` from nested blackboard/ticket/agent_config.
    Works with both AgentState objects and raw dicts.
    """
    blackboard = getattr(state, "blackboard", None) or (
        state.get("blackboard") if isinstance(state, dict) else None
    )
    if not blackboard:
        return False

    ticket = getattr(blackboard, "ticket", None) or (
        blackboard.get("ticket") if isinstance(blackboard, dict) else None
    )
    if not ticket:
        return False

    agent_config = getattr(ticket, "agent_config", None) or (
        ticket.get("agent_config") if isinstance(ticket, dict) else None
    )
    if not agent_config:
        return False

    return getattr(agent_config, "is_subtask", False) or (
        agent_config.get("is_subtask", False) if isinstance(agent_config, dict) else False
    )
