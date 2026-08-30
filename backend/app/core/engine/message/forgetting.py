"""
Soft forgetting utilities for message history.

Replaces content of forgotten tool outputs with lightweight summaries.
"""

from app.core.engine.message.constants import MessageRole
from app.core.engine.message.native_classes import BaseMessage, ToolMessage
from app.core.memory.tool_output_memory import ToolOutputMemory
from app.utils.template import render_template


def apply_forgotten_status(
    messages: list[BaseMessage], tool_memory: ToolOutputMemory
) -> list[BaseMessage]:
    if not tool_memory or not tool_memory.forgotten:
        return messages

    result: list = []
    for msg in messages:
        if msg.role == MessageRole.TOOL:
            tool_call_id = msg.tool_call_id
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

                    summary_msg = ToolMessage(
                        content=summary_content,
                        tool_call_id=tool_call_id,
                        name=msg.name,
                        id=msg.id,
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
        else:
            result.append(msg)

    return result
