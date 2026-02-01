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
    "browser_executor",
    "computer_executor",
    "mobile_executor",
]


@tool
def route_to(target: ROUTING_TARGETS, reason: str, context: dict | None = None) -> str:
    """
    Route the current task to a specialist node.

    Call this tool when you have completed your analysis and are ready to
    hand off to a specialist. This is the ONLY way to proceed to the next step.

    Available targets:
    - "developer": Consolidates planning, coding, and testing. Use this for ANY task involving code modification, bug fixing, or feature implementation.
    - "deep_researcher": Need to search the web or gather more information
    - "documenter": Need to generate documentation, wiki, or README
    - "chat": Need to ask the user clarifying questions (ambiguous request)
    - "finish": The task is complete or the question has been fully answered
    - "browser_executor": Need to interact with web pages
    - "computer_executor": Need to execute system commands
    - "mobile_executor": Need to control mobile devices

    Args:
        target: The specialist node to route to.
        reason: Brief explanation of why.
        context: Structured context to pass to the specialist (Attention Guidance).
                 MUST follow this schema for 'developer' target:
                 {
                    "ticket_type": "bugfix" | "feature" | "refactor",
                    "priority": "high" | "normal",
                    "focus_paths": ["path/to/file.py"],  # CRITICAL: Files you want the dev to read
                    "acceptance_criteria": [              # CRITICAL: How to verify success
                        "Login returns 200 OK",
                        "Error message is displayed"
                    ]
                 }

    Returns:
        Confirmation message (the actual routing is handled by the system)
    """
    # This return value is primarily for logging purposes
    # The actual routing logic is in AgentEngine
    context_str = json.dumps(context, ensure_ascii=False) if context else "{}"
    return f"[ROUTE_SIGNAL] → {target}: {reason} | Context: {context_str}"
