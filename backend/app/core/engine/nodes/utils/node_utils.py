"""
Shared utilities for EvoLoop engine nodes.

Extracts cross-cutting concerns (logging, state resolution, signal dispatch)
to eliminate duplication across BaseAgentNode, FinishNode, AggregatorNode, etc.
"""

import logging
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


def _fmt_msg_summary(msgs: list[BaseMessage] | None, max_content: int = 60) -> dict[str, Any]:
    """Format message list for compact trace logging."""
    if not msgs:
        return {"count": 0, "types": [], "ids": [], "contents": []}
    return {
        "count": len(msgs),
        "types": [type(m).__name__ for m in msgs],
        "ids": [
            getattr(m, "id", "N/A")[:8] if getattr(m, "id", None) else "N/A"
            for m in msgs
        ],
        "contents": [
            str(getattr(m, "content", ""))[:max_content] for m in msgs
        ],
    }


def log_msg_trace(
    node_name: str,
    phase: str,
    messages: list[BaseMessage] | None = None,
    **extra: Any,
) -> None:
    """
    Centralized MSG-TRACE logger.

    Phases:
        ENTER      – node entry, state.messages snapshot
        SHORT-CIRCUIT – early return from prepare_state
        EXECUTION  – after ticket injection, before engine.run_node
        EXIT       – node exit, returned StateUpdate.messages snapshot
        SIGNAL     – signal dispatch path
        PROTOCOL   – protocol violation fallback
        ERROR      – error path
    """
    summary = _fmt_msg_summary(messages)
    parts = [
        f"[MSG-TRACE][{node_name}] {phase}",
        f"state.messages: {summary['count']} msgs",
        f"types={summary['types']}",
        f"ids={summary['ids']}",
    ]
    if messages:
        parts.append(f"contents={summary['contents']}")
    for k, v in extra.items():
        parts.append(f"{k}={v}")
    logger.info(" | ".join(parts))


def log_handle_outcome_trace(
    node_name: str,
    phase: str,
    engine_messages: list[BaseMessage] | None = None,
    signal_type: str | None = None,
    **extra: Any,
) -> None:
    """Trace log specifically for handle_outcome paths."""
    summary = _fmt_msg_summary(engine_messages)
    parts = [
        f"[MSG-TRACE][{node_name}] handle_outcome {phase}",
        f"engine_result.messages={summary['count']} msgs",
        f"types={summary['types']}",
        f"signal={signal_type or 'None'}",
    ]
    for k, v in extra.items():
        parts.append(f"{k}={v}")
    logger.info(" | ".join(parts))


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


async def dispatch_signal_if_present(
    original_state: Any,
    signal: Any,
    config: RunnableConfig,
    node_name: str = "base",
) -> Any | None:
    """
    Centralized signal dispatch. Returns the dispatch_result if a signal
    was present and dispatched, otherwise None.

    Callers should check the return value:
        result = await dispatch_signal_if_present(...)
        if result is not None:
            return result   # signal path
        # continue with non-signal handling...
    """
    if not signal:
        return None

    from app.core.engine.signals import SignalDispatcher

    log_handle_outcome_trace(
        node_name,
        "SIGNAL",
        signal_type=type(signal).__name__,
    )
    dispatch_result = await SignalDispatcher.dispatch(original_state, signal, config)
    out_msgs = getattr(dispatch_result, "messages", None) or []
    log_handle_outcome_trace(
        node_name,
        "SIGNAL_DISPATCHED",
        engine_messages=out_msgs,
        next_node=getattr(dispatch_result, "next_node", "N/A"),
    )
    return dispatch_result
