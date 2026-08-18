"""
Structured Worker outcome reporting.

Replaces brittle text-keyword heuristics with an explicit signal:
Worker reports whether it succeeded, failed, or cannot verify the outcome
because the environment lacks the necessary data/tools.
"""

import json
import logging
from typing import Literal

from app.core.context.manager import ContextManager
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    is_hidden=True,
    summary_template="evoloop.tool_summary.report_outcome",
)
def report_outcome(
    status: Literal["done", "failed", "unverifiable"],
    summary: str,
    topic: str | None = None,
) -> str:
    """
    Report the final outcome of the current Worker mission.

    This is the preferred way for a Worker to tell the Supervisor that the
    mission is finished. Use one of the following statuses:

    - "done": the mission succeeded and `summary` contains the result.
    - "failed": the mission failed and `summary` explains why.
    - "unverifiable": the environment cannot verify the outcome (no MCP / no
      informative macro / no browser read tool). The Supervisor will stop
      re-dispatching verification missions for the same topic.

    Args:
        status: final mission status.
        summary: concise human-readable summary of the result.
        topic: optional topic anchor (defaults to the current ticket topic or
               session goal). Used by the anti-loop guard to match future
               verification requests.
    """
    ctx = ContextManager.current()
    if not ctx or not ctx.metadata.blackboard:
        return "Error: State context not available."

    state = ctx.metadata.blackboard
    shared = dict(state.shared_context or {})

    shared["worker_report_status"] = status
    shared["worker_report_summary"] = summary

    if status == "unverifiable":
        shared["verification_impossible"] = True
        shared["verification_block_reason"] = summary
        blocked_topic = topic or ""
        if not blocked_topic:
            ticket = getattr(state, "ticket", None)
            blocked_topic = (
                getattr(ticket, "topic", None)
                or getattr(state, "session_goal", None)
                or getattr(state, "current_goal", None)
                or ""
            )
        blocked_topic = blocked_topic[:500]

        # Maintain a persistent list of blocked verification topics so that
        # multiple unrelated missions can each be flagged without overwriting
        # earlier blocks.
        blocked_topics = shared.get("verification_blocked_topics") or []
        if not isinstance(blocked_topics, list):
            blocked_topics = []
        if blocked_topic and blocked_topic not in blocked_topics:
            blocked_topics.append(blocked_topic)
        shared["verification_blocked_topics"] = blocked_topics

        # Keep the single-topic key for backward compatibility, but it now
        # reflects the most recently blocked topic.
        shared["verification_blocked_topic"] = blocked_topic
        logger.info(
            "[ReportOutcome] Worker reports mission unverifiable for topic '%s': %s",
            blocked_topic,
            summary[:200],
        )

    state.shared_context = shared
    ctx.metadata.shared_context = shared

    return json.dumps(
        {"reported": True, "status": status, "summary": summary},
        ensure_ascii=False,
    )
