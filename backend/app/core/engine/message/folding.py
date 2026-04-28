"""
Message folding utilities — convert between flat and nested message formats.
"""
import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.engine.reasoning import parse_thinking
from app.core.engine.state.history import FoldedMessage

logger = logging.getLogger(__name__)


def to_base_message(msg: Any) -> BaseMessage | None:
    """
    Convert a database Message record or similar object to a LangChain BaseMessage.
    
    Args:
        msg: Object with role, content, and optionally tool_calls / tool_call_id
        
    Returns:
        A LangChain message object or None if role is unknown
    """
    role = getattr(msg, "role", None)
    # Defensive: content may be None in DB; LangChain v2 rejects None content
    content = getattr(msg, "content", "") or ""

    # Preserve key metadata that fold_messages and other utilities need
    msg_id = str(getattr(msg, "id", "")) or None
    created_at = getattr(msg, "created_at", None)
    thinking_raw = getattr(msg, "thinking", None)

    # Parse thinking from DB: JSON-serialized list[dict]
    thinking = parse_thinking(thinking_raw) if isinstance(thinking_raw, str) else thinking_raw

    # LangChain messages use additional_kwargs for extra metadata.
    # Note: `id` is passed as a top-level constructor arg, NOT inside
    # additional_kwargs, to avoid duplicate-key warnings.
    kwargs: dict[str, Any] = {}
    if created_at:
        kwargs["created_at"] = created_at
    if thinking:
        kwargs["thinking"] = thinking

    try:
        if role == "human":
            return HumanMessage(content=content, id=msg_id, additional_kwargs=kwargs)
        elif role == "ai":
            tool_calls = getattr(msg, "tool_calls", []) or []
            # Defensive: some DB drivers may return JSON as a string
            if isinstance(tool_calls, str):
                try:
                    tool_calls = json.loads(tool_calls)
                except (json.JSONDecodeError, ValueError):
                    tool_calls = []
            if not isinstance(tool_calls, list):
                tool_calls = []
            return AIMessage(
                content=content, 
                id=msg_id,
                tool_calls=tool_calls,
                additional_kwargs=kwargs
            )
        elif role == "tool":
            # For database records, name might be stored in 'tool_name' or derived from tool_calls
            return ToolMessage(
                content=content,
                id=msg_id,
                tool_call_id=getattr(msg, "tool_call_id", "") or "",
                name=getattr(msg, "tool_name", None),
                additional_kwargs=kwargs
            )
        elif role == "system":
            return SystemMessage(content=content, id=msg_id, additional_kwargs=kwargs)
    except Exception as e:
        logger.warning(f"[to_base_message] Failed to convert msg id={msg_id} role={role}: {e}")
        return None

    return None


def fold_messages(messages: list[BaseMessage]) -> list[FoldedMessage]:
    """
    Fold flat message list into nested format with embedded steps.
    
    This version uses MessageFolder for unified logic and supports
    the steps_snapshot fast-path optimization.
    
    Args:
        messages: Flat list of messages (AIMessage, ToolMessage, HumanMessage)
        
    Returns:
        Folded list of FoldedMessage objects
    """
    from app.core.engine.message.folder import MessageFolder
    return MessageFolder.fold(messages)
