"""
Routing Tool for Supervisor ReAct Architecture.

This tool enables the Supervisor LLM to make autonomous routing decisions
as part of its standard ReAct loop, rather than using a separate routing call.
"""

import json
from typing import Any

from app.constants import RoutingTarget
from app.core.tools import evoloop_tool


@evoloop_tool
def route_to(target: RoutingTarget, reason: str, context: dict[str, Any] | None = None) -> str:
    """
    Route the current task to a specialist node.

    Call this tool when you have completed your analysis and are ready to
    hand off to a specialist. This is the ONLY way to proceed to the next step.

    Available targets:
    - "operator": Consolidates planning, coding, testing, and system control.
    - "deep_researcher": Web search and information gathering.
    - "documenter": Generate documentation, wiki, or README.
    - "chat": Ask the user clarifying questions or provide final chat response.
    - "finish": Task completion or question fully answered.
    - "dynamic_specialist": Temporary, specialized sub-agent (e.g., "SQL Runner").
    - "flash_brain": Fast, low-cost reasoning or memory lookup.

    Args:
        target: The specialist node to route to.
        reason: Brief explanation of why.
        context: Structured context to pass to the specialist (Attention Guidance).
    """
    # This return value is primarily for logging purposes
    # The actual routing logic is in AgentEngine
    context_str = json.dumps(context, ensure_ascii=False) if context else "{}"
    target_val = target.value if isinstance(target, RoutingTarget) else target
    return f"[ROUTE_SIGNAL] → {target_val}: {reason} | Context: {context_str}"
