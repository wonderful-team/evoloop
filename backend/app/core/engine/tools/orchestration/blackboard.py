"""
Blackboard Tool — structured shared-state updates via function calling.

Replaces the legacy text-tag pattern [BLACKBOARD: key=value] so that
internal state mutations are never leaked into the user-facing chat stream.
"""

import logging

from app.core.tools.base import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    is_hidden=True,  # Internal signal — must NOT appear in the user's chat stream
    summary_template="evoloop.tool_summary.update_blackboard",
)
def update_blackboard(updates: dict) -> str:
    """
    Persist key-value pairs to the team's shared Blackboard state.

    Use this tool (instead of writing '[BLACKBOARD: key=value]' in plain text)
    whenever you need to save a flag, finding, or intermediate result so that
    subsequent Supervisor / Worker turns can read it.

    Common use cases:
    - Saving database scout results (e.g., {"scout_db": "laomiao_zhiying"})
    - Recording boolean flags   (e.g., {"issue_found": True})
    - Passing routing hints      (e.g., {"business_query_target_db": "adb_qdy"})

    Args:
        updates: A flat dict of {str: any} pairs to write into the Blackboard.
                 String "true"/"false" values are auto-coerced to booleans.
                 Numeric strings are auto-coerced to integers.
    """
    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    if not ctx or not ctx.metadata.blackboard:
        return "Error: Blackboard context not available."

    blackboard = ctx.metadata.blackboard

    # Coerce common string literals to proper Python types
    coerced: dict = {}
    for key, val in updates.items():
        if isinstance(val, str):
            if val.lower() == "true":
                val = True
            elif val.lower() == "false":
                val = False
            elif val.isdigit():
                val = int(val)
        coerced[key] = val

    # Persist into shared_context (survives across turns via blackboard merge)
    shared = dict(blackboard.shared_context or {})
    shared.update({k: str(v) for k, v in coerced.items()})
    blackboard.shared_context = shared

    updated_keys = list(coerced.keys())
    for key, val in coerced.items():
        logger.info(f"[Blackboard] Updated via tool call: '{key}' = {val!r}")

    return f"Blackboard updated successfully. Keys written: {updated_keys}"
