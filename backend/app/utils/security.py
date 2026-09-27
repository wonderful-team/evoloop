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
    "create_access_token",
    "generate_hmac_signature",
    "get_password_hash",
    "mask_sensitive_data",
    "redact_secrets",
    "sanitize_filename",
    "sanitize_string",
    "verify_password",
]
