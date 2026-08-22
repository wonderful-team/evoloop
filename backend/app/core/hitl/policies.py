"""Backward-compatibility re-export of authorization policy models and loader.

The canonical implementation now lives in ``app.core.security.policy_loader``.
New code should import from there.
"""

from app.core.security.policy_loader import (
    DEFAULT_SENSITIVE_PATTERNS,
    AuthorizationPolicy,
    GrantedPermission,
    PolicyLoader,
)

__all__ = [
    "AuthorizationPolicy",
    "GrantedPermission",
    "PolicyLoader",
    "DEFAULT_SENSITIVE_PATTERNS",
]
