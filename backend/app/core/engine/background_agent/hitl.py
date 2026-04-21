"""
Human-in-the-loop (HITL) resume logic for background agent execution.
"""

import logging
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)


async def build_resume_command(
    graph_instance,
    config: dict,
    user_response: str,
) -> Any:
    """
    Build a LangGraph Command for resuming from HITL interrupt.

    Checks the graph state for pending tool calls (request_approval, request_human_input)
    and auto-completes them with the user response.

    Args:
        graph_instance: Compiled LangGraph instance
        config: RunnableConfig dict
        user_response: The user's response text

    Returns:
        Command(resume=...) or the raw user_response
    """
    current_state = await graph_instance.aget_state(config)
    last_tool_call_id = None

    if current_state.values and "messages" in current_state.values:
        history = current_state.values["messages"]
        if history:
            last_msg = history[-1]
            # Check for pending tool calls
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                last_tool_call = last_msg.tool_calls[-1]
                if last_tool_call["name"] in ["request_approval", "request_human_input"]:
                    logger.info(f"Background Resume: Auto-completing tool {last_tool_call['name']}")
                    last_tool_call_id = last_tool_call["id"]

    # Construct Command
    if last_tool_call_id:
        # Resume with Tool Message
        tool_msg = ToolMessage(
            tool_call_id=last_tool_call_id,
            content=str(user_response),
        )
        return Command(resume=tool_msg)

    # Fallback or standard resume
    return Command(resume=user_response)
