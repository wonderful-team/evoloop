"""
Shared message utilities for agent nodes.

Contains common functions for message processing, history repair, and extraction.
"""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, SystemMessage


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
    Ensure the message history is valid for strict LLM APIs (like Anthropic/GLM).
    1. No orphaned ToolMessages (must have preceding AIMessage with tool_calls).
    2. No consecutive messages of same role (Human->Human, AI->AI).
    3. No empty content allowed.
    """
    repaired = []

    for msg in messages:
        # Check for empty content
        if not msg.content and not isinstance(msg, (ToolMessage, AIMessage)):  
            # AI/Tool messages can have tool_calls instead of content
            continue
            
        if isinstance(msg, AIMessage) and not msg.content and not msg.tool_calls:
             continue

        if isinstance(msg, ToolMessage):
            # 1. Orphan Check
            is_orphaned = True
            if repaired:
                last = repaired[-1]
                if isinstance(last, AIMessage) and last.tool_calls:
                    ids = [tc['id'] for tc in last.tool_calls]
                    if msg.tool_call_id in ids:
                        is_orphaned = False

            if is_orphaned:
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
            continue
            
        # 2. Strict Role Alternation (Merge consecutive same-role)
        if repaired:
            last = repaired[-1]
            if type(last) == type(msg) and isinstance(msg, (HumanMessage, AIMessage)):
                # Merge content
                new_content = f"{last.content}\n\n{msg.content}"
                # Update last message in place
                last.content = new_content
                continue
        
        repaired.append(msg)

    # 3. Ensure Conversation Starts with Human (for strict APIs like Zhipu/Anthropic)
    # Find first non-System message
    non_system_indices = [i for i, m in enumerate(repaired) if not isinstance(m, SystemMessage)]
    if non_system_indices:
        first_idx = non_system_indices[0]
        first_msg = repaired[first_idx]
        if isinstance(first_msg, AIMessage):
            # Prepend dummy Human Message to satisfy "User must start" rule
            repaired.insert(first_idx, HumanMessage(content="...continuing conversation context..."))

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

