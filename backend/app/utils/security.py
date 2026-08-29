"""General security-related utilities that do not fit into a dedicated domain.

Crypto/token helpers have moved to ``app.core.security.crypto``.
Secret redaction helpers have moved to ``app.utils.redact``.
Path traversal helpers are available in ``app.utils.path`` and
``app.core.security.path``.

This module is kept as a compatibility/utility layer for:
- filename sanitization
- bundle/package name validation
- URL scheme safety checks
- a simple in-memory rate limiter
"""

import re

# Backward-compatible re-exports for code that has not migrated yet.
# New code should import directly from app.core.security.*.
from app.core.security.crypto import (
    ALGORITHM,
    create_access_token,
    generate_hmac_signature,
    get_password_hash,
    verify_password,
)
from app.utils.filename import sanitize_filename
from app.utils.redact import (
    mask_sensitive_data,
    redact_secrets,
    sanitize_string,
)

__all__ = [
    "ALGORITHM",
    "SimpleRateLimiter",
    "create_access_token",
    "generate_hmac_signature",
    "get_password_hash",
    "is_path_within_base",
    "is_safe_url",
    "mask_sensitive_data",
    "redact_secrets",
    "sanitize_filename",
    "sanitize_string",
    "validate_bundle_id",
    "validate_package_name",
    "verify_password",
]


def is_path_within_base(base_path: str, target_path: str) -> bool:
    """
    Check if target_path is within base_path (prevents directory traversal).

    Args:
        base_path: Base directory path
        target_path: Path to check

    Returns:
        True if target_path is within base_path
    """
    from pathlib import Path

    try:
        base = Path(base_path).resolve()
        target = Path(target_path).resolve()
        return str(target).startswith(str(base))
    except (ValueError, OSError):
        return False


# ============================================================================
# Input Validation
# ============================================================================


def validate_bundle_id(bundle_id: str) -> bool:
    """
    Validate Android/iOS bundle ID format.

    Args:
        bundle_id: Bundle identifier (e.g., 'com.example.app')

    Returns:
        True if valid bundle ID format
    """
    # Bundle ID format: com.company.app (reverse domain notation)
    pattern = r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$"
    return bool(re.match(pattern, bundle_id))


def validate_package_name(name: str) -> bool:
    """
    Validate Android package name.

    Args:
        name: Package name

    Returns:
        True if valid package name
    """
    # Package name: com.company.app, must start with letter, lowercase preferred
    pattern = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
    return bool(re.match(pattern, name))


def is_safe_url(url: str, allowed_schemes: set[str] | None = None) -> bool:
    """
    Check if URL is safe (no file://, javascript:, etc.).

    Args:
        url: URL to check
        allowed_schemes: Set of allowed schemes (default: http, https)

    Returns:
        True if URL appears safe
    """
    if allowed_schemes is None:
        allowed_schemes = {"http", "https"}

    # Check for dangerous schemes
    dangerous_schemes = {"javascript:", "data:", "vbscript:", "file:"}
    lower_url = url.lower().strip()

    for scheme in dangerous_schemes:
        if lower_url.startswith(scheme):
            return False

    # If URL has a scheme, verify it's allowed
    if "://" in url:
        scheme = url.split("://")[0].lower()
        if scheme not in allowed_schemes:
            return False

    return True


# ============================================================================
# Rate Limiting (Simple)
# ============================================================================


class SimpleRateLimiter:
    """
    Simple in-memory rate limiter.

    Example:
        limiter = SimpleRateLimiter(max_calls=10, period=60)
        if limiter.is_allowed("user_123"):
            process_request()
        else:
            raise RateLimitExceeded()
    """

    def __init__(self, max_calls: int, period: float):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed
            period: Time period in seconds
        """
        self.max_calls = max_calls
        self.period = period
        self._calls: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """
        Check if call is allowed for key.

        Args:
            key: Identifier (e.g., user ID, IP address)

        Returns:
            True if call is allowed
        """
        import time

        now = time.time()

        # Get or create call history
        calls = self._calls.get(key, [])

        # Remove old calls outside the period
        calls = [t for t in calls if now - t < self.period]

        # Check if under limit
        if len(calls) < self.max_calls:
            calls.append(now)
            self._calls[key] = calls
            return True

        self._calls[key] = calls
        return False

    def get_remaining(self, key: str) -> int:
        """Get remaining calls for key."""
        import time

        now = time.time()
        calls = self._calls.get(key, [])
        calls = [t for t in calls if now - t < self.period]
        return max(0, self.max_calls - len(calls))

    def reset(self, key: str) -> None:
        """Reset rate limit for key."""
        self._calls.pop(key, None)

    def clear(self) -> None:
        """Clear all rate limits."""
        self._calls.clear()
