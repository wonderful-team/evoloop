"""
Message history repair utilities.

Ensures message history is valid for strict LLM APIs (Anthropic/GLM).
"""

import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.engine.state.history import ToolCall
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


def prune_trailing_errors(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Remove trailing AIMessages that are marked as errors to prevent LLM confusion on retry."""
    while messages and isinstance(messages[-1], AIMessage):
        metadata = getattr(messages[-1], "metadata", {}) or {}
        if metadata.get("is_error"):
            messages.pop()
        else:
            break
    return messages


def repair_message_history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Ensure the message history is valid for strict LLM APIs (like Anthropic/GLM).
    1. No orphaned ToolMessages (must have preceding AIMessage with tool_calls).
    2. No dangling ToolCalls (must be followed by ToolMessages).
    3. No consecutive messages of same role (Human->Human, AI->AI).
    4. No empty content allowed.

    Args:
        messages: The message list to repair.
    """
    # Default message templates
    defaults = {
        "orphaned_tool": "[Tool execution context missing]",
        "interrupted_tool_response": "[Tool execution was interrupted]",
        "conversation_continuation": "[Conversation continues]",
    }

    def get_msg(key: str) -> str:
        """Get translated message with fallback to defaults."""
        try:
            result = i18n.get(f"core_utils.{key}", default=defaults[key])
            return result if isinstance(result, str) else defaults[key]
        except Exception:
            return defaults[key]

    # Phase 1: Basic cleanup & Orphaned ToolMessage repair
    stage1 = []
    for msg in messages:
        # Check for empty content
        if not msg.content and not isinstance(msg, ToolMessage | AIMessage):
            # AI/Tool messages can have tool_calls instead of content
            continue

        if isinstance(msg, AIMessage) and not msg.content and not msg.tool_calls:
            continue

        if isinstance(msg, ToolMessage):
            # Orphan Check
            is_orphaned = True
            if stage1:
                last = stage1[-1]
                if isinstance(last, AIMessage) and last.tool_calls:
                    ids = [tc['id'] if isinstance(tc, dict) else tc.id for tc in last.tool_calls]
                    if msg.tool_call_id in ids:
                        is_orphaned = False

            if is_orphaned:
                dummy = AIMessage(
                    content=get_msg("orphaned_tool"),
                    tool_calls=[ToolCall(
                        id=msg.tool_call_id,
                        name=msg.name or "unknown_tool",
                        args={}
                    ).model_dump()]
                )
                stage1.append(dummy)

            stage1.append(msg)
            continue

        # Strict Role Alternation (Merge consecutive same-role)
        if stage1:
            last = stage1[-1]
            # Use isinstance for subclass compatibility
            if isinstance(last, type(msg)) and isinstance(msg, HumanMessage | AIMessage):
                # Skip merge if last message has tool_calls to preserve structure
                if isinstance(last, AIMessage) and getattr(last, 'tool_calls', None):
                    stage1.append(msg)
                    continue
                # Skip merge if either message is a context_ticket (injected synthetic message)
                if (getattr(last, 'name', None) == 'context_ticket' or
                        getattr(msg, 'name', None) == 'context_ticket'):
                    stage1.append(msg)
                    continue
                # Merge content — create a NEW message object to avoid mutating
                # the original, which may be a shared reference in LangGraph state.
                new_content = f"{last.content}\n\n{msg.content}"
                merged = last.model_copy(update={"content": new_content})
                stage1[-1] = merged
                continue

        stage1.append(msg)

    # Phase 2: Dangling ToolCall repair (AIMessage with tool_calls must be followed by ToolMessages)
    final_repaired = []
    open_tool_calls = {}  # id -> name

    for i, msg in enumerate(stage1):
        # If we see a Human/AI message but have open tool calls from previous AI message,
        # we MUST close them first (Anthropic requirement).
        if isinstance(msg, HumanMessage | AIMessage) and open_tool_calls:
            for tcid, tname in list(open_tool_calls.items()):
                final_repaired.append(ToolMessage(
                    content=get_msg("interrupted_tool_response"),
                    tool_call_id=tcid,
                    name=tname
                ))
            open_tool_calls = {}

        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                # Still handle dict access for raw LangChain messages, but remove redundant validation
                tcid = tc['id'] if isinstance(tc, dict) else tc.id
                tname = tc['name'] if isinstance(tc, dict) else tc.name
                open_tool_calls[tcid] = tname

        if isinstance(msg, ToolMessage):
            # Clear opened call
            if msg.tool_call_id in open_tool_calls:
                del open_tool_calls[msg.tool_call_id]

        final_repaired.append(msg)

    # Final check for trailing tool calls (history cannot end with AIMessage(tool_calls))
    if open_tool_calls and final_repaired:
        logger.warning("🔧 [Repair] History ends with dangling tool calls. Injecting dummy responses.")
        for tcid, tname in list(open_tool_calls.items()):
            final_repaired.append(ToolMessage(
                content=i18n.get("core_utils.interrupted_tool_response"),
                tool_call_id=tcid,
                name=tname
            ))

    # Phase 4: Start with Human
    non_system_indices = [idx for idx, m in enumerate(final_repaired) if not isinstance(m, SystemMessage)]
    if non_system_indices:
        first_idx = non_system_indices[0]
        if isinstance(final_repaired[first_idx], AIMessage):
            final_repaired.insert(first_idx, HumanMessage(content=get_msg("conversation_continuation")))
    elif not final_repaired:
        final_repaired.append(HumanMessage(content=get_msg("conversation_continuation")))

    return final_repaired
