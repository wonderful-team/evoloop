"""
Human-in-the-loop (HITL) resume logic for background agent execution.
"""

import logging
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.core.engine.hitl import get_pending_hitl_call

logger = logging.getLogger(__name__)


async def build_resume_command(
    graph_instance,
    config: dict,
    user_response: str,
) -> Any:
    """
    Build a LangGraph Command for resuming from HITL interrupt.
    """
    from app.core.engine.hitl import HITLOrchestrator
    thread_id = config.get("configurable", {}).get("thread_id")

    # Detect pending tool call via standardized orchestrator
    pending_tool = await get_pending_hitl_call(graph_instance, config)

    if pending_tool:
        logger.info(f"Background Resume: Auto-completing tool {pending_tool['name']}")
        
        # Standardized normalization and DB state closure
        normalized_input = await HITLOrchestrator.handle_resume(
            thread_id=thread_id,
            tool_call=pending_tool,
            user_input=user_response
        )

        # Resume with Tool Message
        tool_msg = ToolMessage(
            tool_call_id=pending_tool["id"],
            content=normalized_input,
        )
        return Command(resume=tool_msg)

    # Fallback or standard resume
    return Command(resume=user_response)
