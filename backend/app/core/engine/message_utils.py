"""
Shared message utilities for agent nodes.

Contains common functions for message processing, history repair, and extraction.
"""

import logging

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.constants import MAX_OUTPUT_LENGTH
from app.i18n.service import i18n
from app.infrastructure.llm.model_profile import get_profile

logger = logging.getLogger(__name__)

# Legacy fallback constant
_DEFAULT_WINDOW_SIZE = 30


def _get_truncate_limit(model: str | None = None) -> int:
    """Get truncate limit from ModelProfile, falling back to MAX_OUTPUT_LENGTH."""
    try:
        profile = get_profile(model) if model else None
        if profile:
            return profile.truncate_limit_chars
    except ImportError:
        pass
    return MAX_OUTPUT_LENGTH


def _get_window_size(model: str | None = None) -> int:
    """Get window size from ModelProfile, falling back to default."""
    try:
        profile = get_profile(model) if model else None
        if profile:
            return profile.window_size
    except ImportError:
        pass
    return _DEFAULT_WINDOW_SIZE


def truncate_message_content(
    content: str,
    limit: int | None = None,
    model: str | None = None,
) -> str:
    """
    Truncate content if it exceeds the limit, adding a metadata footer.
    
    Args:
        content: The content string to truncate.
        limit: Explicit character limit. If None, derived from ModelProfile or MAX_OUTPUT_LENGTH.
        model: Model name for profile-aware limit derivation.
    """
    effective_limit = limit or _get_truncate_limit(model)

    if not content or len(content) <= effective_limit:
        return content

    chars = len(content)
    lines = content.count("\n")
    truncated = content[:effective_limit]

    # Add a suffix that the LLM understands as a truncation signal
    footer = f"\n...\n[Output truncated: {lines} lines / {chars} chars total. Use specific read/search tools for more.]"
    return truncated + footer


def get_message_text(message: BaseMessage | str) -> str:
    """
    Robustly extract text content from a message object, handling:
    - Normal string content
    - List of blocks (Multimodal/Anthropic)
    """
    if isinstance(message, str):
        return message

    content = message.content
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        # Join all text blocks
        text_parts = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict):
                # Anthropic style: {"type": "text", "text": "..."}
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
        return "\n".join(text_parts)

    return ""


def get_last_human_message(messages: list) -> str | None:
    """Extract the last human message content from a message list."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return get_message_text(msg)
    return None


def repair_message_history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Ensure the message history is valid for strict LLM APIs (like Anthropic/GLM).
    1. No orphaned ToolMessages (must have preceding AIMessage with tool_calls).
    2. No dangling ToolCalls (must be followed by ToolMessages).
    3. No consecutive messages of same role (Human->Human, AI->AI).
    4. No empty content allowed.
    """
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
                    ids = [tc["id"] for tc in last.tool_calls]
                    if msg.tool_call_id in ids:
                        is_orphaned = False

            if is_orphaned:
                dummy = AIMessage(
                    content=i18n.get("prompts.core_utils.orphaned_tool"),
                    tool_calls=[{
                        "id": msg.tool_call_id,
                        "name": msg.name or "unknown_tool",
                        "args": {}
                    }]
                )
                stage1.append(dummy)

            stage1.append(msg)
            continue

        # Strict Role Alternation (Merge consecutive same-role)
        if stage1:
            last = stage1[-1]
            if type(last) is type(msg) and isinstance(msg, HumanMessage | AIMessage):
                # Merge content
                new_content = f"{last.content}\n\n{msg.content}"
                last.content = new_content
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
                    content="[System: Result omitted or context interrupted. Respond to remaining context.]",
                    tool_call_id=tcid,
                    name=tname
                ))
            open_tool_calls = {}

        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                open_tool_calls[tc["id"]] = tc["name"]

        if isinstance(msg, ToolMessage):
            # Clear opened call
            if msg.tool_call_id in open_tool_calls:
                del open_tool_calls[msg.tool_call_id]

        final_repaired.append(msg)

    # Phase 3: Final check for trailing tool calls (history cannot end with AIMessage(tool_calls))
    if open_tool_calls and final_repaired:
        # If the very last message has dangling calls, we scrub them from that message
        # rather than appending dummy ToolMessages (better for model continuation).
        last = final_repaired[-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            # Only keep tool calls that matched ToolMessages (which should be none if they are in open_tool_calls)
            last.tool_calls = [tc for tc in last.tool_calls if tc["id"] not in open_tool_calls]
            if not last.content and not last.tool_calls:
                final_repaired.pop()

    # Phase 4: Start with Human
    non_system_indices = [idx for idx, m in enumerate(final_repaired) if not isinstance(m, SystemMessage)]
    if non_system_indices:
        first_idx = non_system_indices[0]
        if isinstance(final_repaired[first_idx], AIMessage):
            final_repaired.insert(first_idx, HumanMessage(content=i18n.get("prompts.core_utils.conversation_continuation")))
    elif not final_repaired:
        final_repaired.append(HumanMessage(content=i18n.get("prompts.core_utils.conversation_continuation")))

    return final_repaired


def smart_window_slice(
    messages: list[BaseMessage],
    window_size: int | None = None,
    model: str | None = None,
) -> list[BaseMessage]:
    """
    Slice the message list to a window size, ensuring no (AI -> Tool) pair is split.
    If the window start falls on a ToolMessage, it backtracks to include the parent AIMessage.

    Args:
        messages: Full list of messages.
        window_size: Explicit window size. If None, derived from ModelProfile.
        model: Model name for profile-aware window sizing.

    Returns:
        Sliced list of messages.
    """
    effective_window = window_size or _get_window_size(model)

    if len(messages) <= effective_window:
        return messages

    start_index = max(0, len(messages) - effective_window)

    # If we are cutting off, and the first message in window is a ToolMessage,
    # step back to include the parent AIMessage (if possible).
    # We check if start_index points to a ToolMessage.
    while start_index > 0 and isinstance(messages[start_index], ToolMessage):
        start_index -= 1

    # Slice
    sliced_msgs = messages[start_index:]

    # Enhance: Preserve the First Human Message (User Goal) if it was sliced out
    # This ensures Supervisor keeps the original context/intent.
    first_human_msg = next((m for m in messages if isinstance(m, HumanMessage)), None)
    if first_human_msg and first_human_msg not in sliced_msgs:
        sliced_msgs.insert(0, first_human_msg)

    return sliced_msgs
