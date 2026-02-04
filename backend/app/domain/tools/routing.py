"""
Routing Tool for Supervisor ReAct Architecture.

This tool enables the Supervisor LLM to make autonomous routing decisions
as part of its standard ReAct loop, rather than using a separate routing call.
"""

import json
from typing import Literal

from langchain_core.tools import tool

# Define valid routing targets
ROUTING_TARGETS = Literal[
    "developer",
    "deep_researcher",
    "documenter",
    "chat",
    "finish",
    "dynamic_specialist", # New v4.0 target
    "flash_brain", # SSM Integration
]


@tool
def route_to(target: ROUTING_TARGETS, reason: str, context: dict | None = None) -> str:
    """
    Route the current task to a specialist node.

    Call this tool when you have completed your analysis and are ready to
    hand off to a specialist. This is the ONLY way to proceed to the next step.

    Available targets:
    - "developer": Consolidates planning, coding, testing, mobile (Android) and desktop (Mac) control. Use this for ANY technical implementation task.
    - "deep_researcher": Need to search the web or gather more information
    - "documenter": Need to generate documentation, wiki, or README
    - "chat": Need to ask the user clarifying questions (ambiguous request)
    - "finish": The task is complete or the question has been fully answered
    - "dynamic_specialist": Need a specialized, temporary sub-agent (e.g., "SQL Runner", "Log Analyzer")
    - "flash_brain": Need fast, low-cost reasoning or memory lookup (Use for simple queries or fact retrieval)

    Args:
        target: The specialist node to route to.
        reason: Brief explanation of why.
        context: Structured context to pass to the specialist (Attention Guidance).
                 MUST follow the appropriate schema for the target.

                 **For 'developer'**:
                 {
                    "ticket_type": "bugfix" | "feature",
                    "focus_paths": ["src/app.py"],
                    "acceptance_criteria": ["Test pass"]
                 }

                 **For 'deep_researcher'**:
                 {
                    "ticket_type": "research",
                    "topic": "How to use Redis with LangGraph",
                    "acceptance_criteria": ["Detailed report with code examples"]
                 }

                 **For 'documenter'**:
                 {
                    "ticket_type": "documentation",
                    "focus_paths": ["src/api/"],
                    "acceptance_criteria": ["README updated"]
                 }

                 **For 'dynamic_specialist'**:
                 {
                    "ticket_type": "adhoc_task",
                    "agent_config": {
                        "role_name": "SQL Runner",
                        "system_instructions": "Execute SQL queries only.",
                        "tools": ["sql_query"]
                    },
                    "acceptance_criteria": ["Query result returned"]
                 }

    Returns:
        Confirmation message (the actual routing is handled by the system)
    """
    # This return value is primarily for logging purposes
    # The actual routing logic is in AgentEngine
    context_str = json.dumps(context, ensure_ascii=False) if context else "{}"
    return f"[ROUTE_SIGNAL] → {target}: {reason} | Context: {context_str}"
