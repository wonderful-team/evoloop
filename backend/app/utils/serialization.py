"""
Serialization Utilities

Provides functions for serializing and deserializing data,
with special handling for LangChain messages and other complex types.
"""

import json
from datetime import date, datetime
from typing import Any


def serialize_datetime(obj: Any) -> str:
    """JSON serializer for datetime objects."""
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def safe_json_dumps(
    obj: Any,
    ensure_ascii: bool = False,
    indent: int | None = None,
    default: Any = None
) -> str:
    """
    Safely serialize object to JSON string with datetime support.
    
    Args:
        obj: Object to serialize
        ensure_ascii: Whether to escape non-ASCII characters
        indent: Indentation level for pretty printing
        default: Optional default serialization function
    
    Returns:
        JSON string
    """
    if default is None:
        default = serialize_datetime
    
    return json.dumps(
        obj,
        ensure_ascii=ensure_ascii,
        indent=indent,
        default=default
    )


def safe_json_loads(s: str | bytes) -> Any:
    """
    Safely parse JSON string with error handling.
    
    Args:
        s: JSON string or bytes
    
    Returns:
        Parsed object, or None if parsing fails
    """
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


# LangChain message serialization (optional, only if langchain is available)
try:
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False


def serialize_message(message: "BaseMessage") -> dict[str, Any]:
    """
    Serialize a LangChain message to a dictionary.
    
    Args:
        message: LangChain message object
    
    Returns:
        Serialized message dict
    """
    if not HAS_LANGCHAIN:
        raise ImportError("LangChain is required for message serialization")
    
    data: dict[str, Any] = {
        "type": message.__class__.__name__,
        "content": message.content,
    }
    
    # Add additional fields based on message type
    # For ToolMessage, tool_call_id is required
    if isinstance(message, ToolMessage):
        data["tool_call_id"] = message.tool_call_id
        data["name"] = message.name
    elif getattr(message, "type", "") == "tool":
        data["tool_call_id"] = getattr(message, "tool_call_id", "")
        data["name"] = getattr(message, "name", "")

    # For AIMessage, tool_calls may exist
    if isinstance(message, AIMessage):
        data["tool_calls"] = message.tool_calls
    elif getattr(message, "type", "") == "ai":
        data["tool_calls"] = getattr(message, "tool_calls", [])
    
    # Include additional_kwargs
    if message.additional_kwargs:
        data["additional_kwargs"] = message.additional_kwargs
    
    return data


def deserialize_message(data: dict[str, Any]) -> "BaseMessage":
    """
    Deserialize a dictionary to a LangChain message.
    
    Args:
        data: Serialized message dict
    
    Returns:
        LangChain message object
    """
    if not HAS_LANGCHAIN:
        raise ImportError("LangChain is required for message deserialization")
    
    msg_type = data.get("type", "HumanMessage")
    content = data.get("content", "")
    additional_kwargs = data.get("additional_kwargs", {})
    
    if msg_type == "HumanMessage":
        return HumanMessage(content=content, additional_kwargs=additional_kwargs)
    elif msg_type == "AIMessage":
        tool_calls = data.get("tool_calls", [])
        return AIMessage(
            content=content,
            tool_calls=tool_calls,
            additional_kwargs=additional_kwargs
        )
    elif msg_type == "SystemMessage":
        return SystemMessage(content=content, additional_kwargs=additional_kwargs)
    elif msg_type == "ToolMessage":
        return ToolMessage(
            content=content,
            tool_call_id=data.get("tool_call_id", ""),
            name=data.get("name", ""),
            additional_kwargs=additional_kwargs
        )
    else:
        # Default to HumanMessage for unknown types
        return HumanMessage(content=content, additional_kwargs=additional_kwargs)


def serialize_messages(messages: list["BaseMessage"]) -> list[dict[str, Any]]:
    """
    Serialize a list of LangChain messages.
    
    Args:
        messages: List of messages
    
    Returns:
        List of serialized message dicts
    """
    return [serialize_message(m) for m in messages]


def deserialize_messages(data: list[dict[str, Any]]) -> list["BaseMessage"]:
    """
    Deserialize a list of message dicts.
    
    Args:
        data: List of serialized message dicts
    
    Returns:
        List of message objects
    """
    return [deserialize_message(d) for d in data]


class MessageSerializer:
    """
    Utility class for serializing/deserializing messages with optional compression.
    """
    
    @staticmethod
    def to_json(messages: list["BaseMessage"], indent: int | None = None) -> str:
        """
        Serialize messages to JSON string.
        
        Args:
            messages: List of messages
            indent: Optional indentation for pretty printing
        
        Returns:
            JSON string
        """
        data = serialize_messages(messages)
        return safe_json_dumps(data, indent=indent)
    
    @staticmethod
    def from_json(json_str: str) -> list["BaseMessage"]:
        """
        Deserialize messages from JSON string.
        
        Args:
            json_str: JSON string
        
        Returns:
            List of messages
        """
        data = safe_json_loads(json_str)
        if data is None:
            return []
        return deserialize_messages(data)
    
    @staticmethod
    def to_dict_list(messages: list["BaseMessage"]) -> list[dict[str, Any]]:
        """Convert messages to list of dicts."""
        return serialize_messages(messages)
    
    @staticmethod
    def from_dict_list(data: list[dict[str, Any]]) -> list["BaseMessage"]:
        """Convert list of dicts to messages."""
        return deserialize_messages(data)


# ============================================================================
# Generic Object Serialization
# ============================================================================


def safe_serialize(obj: Any, max_depth: int = 10, current_depth: int = 0) -> Any:
    """
    Safely serialize an object to JSON-compatible format.
    Handles nested structures, datetime objects, and other common types.
    
    Args:
        obj: Object to serialize
        max_depth: Maximum recursion depth
        current_depth: Current recursion depth (internal use)
    
    Returns:
        JSON-compatible representation
    """
    if current_depth >= max_depth:
        return str(obj)
    
    if obj is None:
        return None
    
    if isinstance(obj, (str, int, float, bool)):
        return obj
    
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    
    if isinstance(obj, bytes):
        try:
            return obj.decode('utf-8')
        except UnicodeDecodeError:
            return f"<bytes: {len(obj)}>"
    
    if isinstance(obj, list | tuple):
        return [
            safe_serialize(item, max_depth, current_depth + 1)
            for item in obj
        ]
    
    if isinstance(obj, dict):
        return {
            str(k): safe_serialize(v, max_depth, current_depth + 1)
            for k, v in obj.items()
        }
    
    if isinstance(obj, set):
        return list(obj)
    
    # Try to get dict representation
    if hasattr(obj, '__dict__'):
        return safe_serialize(obj.__dict__, max_depth, current_depth + 1)
    
    # Fall back to string representation
    return str(obj)


def to_json_string(obj: Any, indent: int | None = None) -> str:
    """
    Convert any object to JSON string with safe serialization.
    
    Args:
        obj: Object to convert
        indent: Optional indentation
    
    Returns:
        JSON string
    """
    serializable = safe_serialize(obj)
    return json.dumps(serializable, indent=indent, ensure_ascii=False)
