"""
Logging Helper Utilities

Provides common logging utilities for formatting and normalizing log content.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def normalize_log_content(content: Any) -> str:
    """
    Normalize content for logging by handling JSON, dicts, and strings.
    
    Args:
        content: Content to normalize (dict, list, str, or other)
    
    Returns:
        Normalized string representation
    
    Examples:
        >>> normalize_log_content({"a": 1})
        '{"a": 1}'
        >>> normalize_log_content("hello")
        'hello'
        >>> normalize_log_content("{'a': 1}")  # Python literal
        '{"a": 1}'
    """
    if content is None:
        return ""
    
    if isinstance(content, str):
        # Try to parse as JSON first
        if content.strip().startswith(("{", "[")):
            try:
                parsed = json.loads(content)
                return json.dumps(parsed, sort_keys=True, ensure_ascii=False)
            except json.JSONDecodeError:
                # Try Python literal eval for single-quoted dicts
                if "'" in content:
                    try:
                        import ast
                        parsed = ast.literal_eval(content)
                        return json.dumps(parsed, sort_keys=True, ensure_ascii=False)
                    except (ValueError, SyntaxError):
                        pass
        return content.strip()
    
    # For dicts, lists, etc.
    try:
        return json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(content)


def format_tool_call(name: str, args: dict[str, Any]) -> str:
    """
    Format a tool call for logging.
    
    Args:
        name: Tool name
        args: Tool arguments
    
    Returns:
        Formatted string like "tool_name({arg1: val1, arg2: val2})"
    """
    args_str = json.dumps(args, ensure_ascii=False, default=str)
    return f"{name}({args_str[:120]}{'...' if len(args_str) > 120 else ''})"


def format_execution_time(start_time: float, end_time: float | None = None) -> str:
    """
    Format execution time for logging.
    
    Args:
        start_time: Start timestamp from time.time()
        end_time: End timestamp (default: current time)
    
    Returns:
        Formatted duration string
    """
    import time
    if end_time is None:
        end_time = time.time()
    
    duration_ms = (end_time - start_time) * 1000
    
    if duration_ms < 1000:
        return f"{duration_ms:.0f}ms"
    elif duration_ms < 60000:
        return f"{duration_ms/1000:.1f}s"
    else:
        minutes = int(duration_ms / 60000)
        seconds = (duration_ms % 60000) / 1000
        return f"{minutes}m {seconds:.1f}s"


def truncate_for_log(
    text: str,
    max_len: int = 500,
    suffix: str = "..."
) -> str:
    """
    Truncate text for logging purposes.
    
    Args:
        text: Text to truncate
        max_len: Maximum length
        suffix: Suffix to add when truncated
    
    Returns:
        Truncated text
    """
    if len(text) <= max_len:
        return text
    return text[:max_len] + suffix


def format_dict_for_log(
    data: dict[str, Any],
    max_value_len: int = 100,
    max_items: int = 10
) -> str:
    """
    Format dictionary for logging with truncation.
    
    Args:
        data: Dictionary to format
        max_value_len: Maximum length for each value
        max_items: Maximum number of items to show
    
    Returns:
        Formatted string representation
    """
    items = []
    for i, (key, value) in enumerate(data.items()):
        if i >= max_items:
            items.append(f"... and {len(data) - max_items} more items")
            break
        
        value_str = str(value)
        if len(value_str) > max_value_len:
            value_str = value_str[:max_value_len] + "..."
        
        items.append(f"{key}={value_str}")
    
    return "{" + ", ".join(items) + "}"


def sanitize_sensitive_data(
    data: dict[str, Any],
    sensitive_keys: tuple[str, ...] = ("password", "token", "secret", "api_key", "key")
) -> dict[str, Any]:
    """
    Sanitize sensitive data in dictionary for logging.
    
    Args:
        data: Dictionary potentially containing sensitive data
        sensitive_keys: Keys to mask
    
    Returns:
        Sanitized dictionary copy
    """
    result = {}
    
    for key, value in data.items():
        if any(sk in key.lower() for sk in sensitive_keys):
            result[key] = "***REDACTED***"
        elif isinstance(value, dict):
            result[key] = sanitize_sensitive_data(value, sensitive_keys)
        else:
            result[key] = value
    
    return result
