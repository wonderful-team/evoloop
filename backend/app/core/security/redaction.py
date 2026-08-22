"""Data sanitization and secret redaction helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

_REDACTED = "******"


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """
    Sanitize a string value for safe storage/display.

    Args:
        value: String to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string
    """
    # Remove control characters except common whitespace
    sanitized = "".join(char for char in value if char >= " " or char in "\t\n\r")

    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive data showing only last few characters.

    Args:
        data: Sensitive data string
        visible_chars: Number of characters to show at end

    Returns:
        Masked string (e.g., '****1234')
    """
    if len(data) <= visible_chars:
        return "*" * len(data)

    return "*" * (len(data) - visible_chars) + data[-visible_chars:]


def redact_secrets(value: Any, secrets: Sequence[str]) -> Any:
    """Replace every occurrence of ``secrets`` inside ``value`` with ``******``.

    Recursively handles strings, dicts and lists; any other type is returned
    unchanged. Empty secrets are skipped. Non-string containers are never
    mutated in place — a sanitized copy is returned.
    """
    if not secrets:
        return value
    if isinstance(value, str):
        sanitized = value
        for secret in secrets:
            if secret and secret in sanitized:
                sanitized = sanitized.replace(secret, _REDACTED)
        return sanitized
    if isinstance(value, dict):
        return {k: redact_secrets(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_secrets(x, secrets) for x in value]
    return value
