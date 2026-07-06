"""
Soft forgetting utilities for message history.

Replaces content of forgotten tool outputs with lightweight summaries.
"""

from app.core.engine.message.native_classes import BaseMessage, ToolMessage
from app.core.memory.tool_output_memory import ToolOutputMemory
from app.utils.template import render_template


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

    result: list = []
    for msg in messages:
        msg_role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "")
        if msg_role == "tool":
            tool_call_id = msg.get("tool_call_id") if isinstance(msg, dict) else getattr(msg, "tool_call_id", None)
            if tool_call_id and tool_memory.is_forgotten(tool_call_id):
                record = tool_memory.get_forgotten_info(tool_call_id)
                if record:
                    summary_content = render_template(
                        "core/engine/fragments/forgotten_summary.j2",
                        tool_name=record.tool_name,
                        original_length=record.original_length,
                        reason=record.reason,
                        summary=record.summary,
                        tool_call_id=tool_call_id,
                    )

                    msg_name = msg.get("name") if isinstance(msg, dict) else getattr(msg, "name", None)
                    msg_id = msg.get("id") if isinstance(msg, dict) else getattr(msg, "id", None)
                    msg_ak = msg.get("additional_kwargs") if isinstance(msg, dict) else getattr(msg, "additional_kwargs", {})

                    summary_msg = ToolMessage(
                        content=summary_content,
                        tool_call_id=tool_call_id,
                        name=msg_name,
                        id=msg_id,
                        additional_kwargs={
                            **(msg_ak or {}),
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
        else:
            result.append(msg)

    return result
