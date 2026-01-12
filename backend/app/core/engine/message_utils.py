"""
Shared message utilities for agent nodes.

Contains common functions for message processing, history repair, and extraction.
"""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def get_last_human_message(messages: list) -> str | None:
    """Extract the last human message content from a message list."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                # Handle Multimodal content
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")
    return None


def repair_message_history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Ensure no ToolMessage is orphaned (without preceding AIMessage with tool_calls).
    If found, insert a dummy AIMessage to satisfy API requirements.
    
    Args:
        messages: List of messages to repair
        
    Returns:
        Repaired message list with no orphaned ToolMessages
    """
    repaired = []

    for msg in messages:
        if isinstance(msg, ToolMessage):
            # Check if previous message has matching tool_call
            is_orphaned = True
            if repaired:
                last = repaired[-1]
                if isinstance(last, AIMessage) and last.tool_calls:
                    # Check ID match
                    ids = [tc['id'] for tc in last.tool_calls]
                    if msg.tool_call_id in ids:
                        is_orphaned = False

            if is_orphaned:
                # Insert Dummy AIMessage
                dummy = AIMessage(
                    content="Executing tool...",
                    tool_calls=[{
                        "id": msg.tool_call_id,
                        "name": msg.name or "unknown_tool",
                        "args": {}
                    }]
                )
                repaired.append(dummy)

        repaired.append(msg)

    return repaired


def truncate_messages(messages: list[BaseMessage], max_messages: int = 20) -> list[BaseMessage]:
    """
    Truncate message history to the last N messages while preserving structure.
    Always keeps the first message (usually system context) and last N-1 messages.
    """
    if len(messages) <= max_messages:
        return messages

    # Keep first message + last (max_messages - 1)
    return [messages[0]] + messages[-(max_messages - 1):]


def smart_window_slice(messages: list[BaseMessage], window_size: int = 30) -> list[BaseMessage]:
    """
    Slice the message list to a window size, ensuring no (AI -> Tool) pair is split.
    If the window start falls on a ToolMessage, it backtracks to include the parent AIMessage.
    
    Args:
        messages: Full list of messages.
        window_size: Desired window size.
        
    Returns:
        Sliced list of messages.
    """
    if len(messages) <= window_size:
        return messages

    start_index = max(0, len(messages) - window_size)

    # If we are cutting off, and the first message in window is a ToolMessage,
    # step back to include the parent AIMessage (if possible).
    # We check if start_index points to a ToolMessage.
    while start_index > 0 and isinstance(messages[start_index], ToolMessage):
            start_index -= 1

    return messages[start_index:]

