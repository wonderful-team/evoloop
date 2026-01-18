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
    "planner",
    "coder", 
    "tester",
    "deep_researcher",
    "documenter",
    "chat",
    "finish",
    "browser_executor",
    "computer_executor",
    "mobile_executor"
]


@tool
def route_to(target: ROUTING_TARGETS, reason: str, context: dict = {}) -> str:
    """
    Route the current task to a specialist node.
    
    Call this tool when you have completed your analysis and are ready to 
    hand off to a specialist. This is the ONLY way to proceed to the next step.
    
    Available targets:
    - "planner": Task is complex and needs architectural planning before coding
    - "coder": You have a clear plan and the task is ready for implementation
    - "tester": User wants to run tests or verify code
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
                 Schema:
                 - focus_paths: list[str] (Files the specialist MUST look at/edit)
                 - constraints: list[str] (Specific limitations)
    
    Returns:
        Confirmation message (the actual routing is handled by the system)
    """
    # This return value is primarily for logging purposes
    # The actual routing logic is in AgentEngine
    context_str = json.dumps(context, ensure_ascii=False) if context else "{}"
    return f"[ROUTE_SIGNAL] → {target}: {reason} | Context: {context_str}"


# Note: Routing tool identification is done by name check in AgentEngine
# (tc["name"] == "route_to") rather than a marker attribute
