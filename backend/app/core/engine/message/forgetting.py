"""
Soft forgetting utilities for message history.

Replaces content of forgotten tool outputs with lightweight summaries.
"""

from langchain_core.messages import BaseMessage, ToolMessage

from app.core.memory.tool_output_memory import ToolOutputMemory
from app.utils import render_template


def apply_forgotten_status(messages: list[BaseMessage], tool_memory: ToolOutputMemory) -> list[BaseMessage]:
    """
    Apply forgotten status to messages based on ToolOutputMemory.

    Replaces content of forgotten tool outputs with their summaries.
    This implements "soft forgetting" - we keep the message structure
    but replace the heavy content with a lightweight summary.

    Args:
        messages: Original message list
        tool_memory: ToolOutputMemory with forgotten records

    Returns:
        Messages with forgotten ones replaced by summaries
    """
    if not tool_memory or not tool_memory.forgotten:
        return messages

    result: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and tool_memory.is_forgotten(msg.tool_call_id):
            # Get summary and replace content
            record = tool_memory.get_forgotten_info(msg.tool_call_id)
            if record:
                # Create a summary message that maintains the tool structure
                # but replaces heavy content with lightweight summary
                summary_content = render_template(
                    "core/engine/fragments/forgotten_summary.j2",
                    tool_name=record.tool_name,
                    original_length=record.original_length,
                    reason=record.reason,
                    summary=record.summary,
                    tool_call_id=msg.tool_call_id,
                )

                # Create new ToolMessage with summary instead of full content
                summary_msg = ToolMessage(
                    content=summary_content,
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                    id=msg.id,
                    # Preserve metadata for tracking
                    additional_kwargs={
                        **(msg.additional_kwargs or {}),
                        "forgotten": True,
                        "original_length": record.original_length,
                        "forgotten_reason": record.reason,
                    },
                )
                result.append(summary_msg)
            else:
                result.append(msg)
        else:
            result.append(msg)

    return result
