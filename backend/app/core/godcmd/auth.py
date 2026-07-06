"""
Godcmd auth — admin user identification.

Supports two sources:
1. User.is_superuser (populated from Member Center or local config)
2. ADMIN_MEMBER_IDS config key (comma-separated member IDs in SystemConfig)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_admin_ids_from_config() -> set[int]:
    """Read ADMIN_MEMBER_IDS from SystemConfig (comma-separated)."""
    try:
        from app.infrastructure.config.service import SystemConfigService
        raw = SystemConfigService.get_value("ADMIN_MEMBER_IDS", "")
        if not raw:
            return set()
        return {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
        return set()


async def is_admin_user(user: Any | None) -> bool:
    """
    Check if a user is an admin (authorized for godcmd commands).

    Args:
        user: The User object (from get_current_user), or None.

    Returns:
        True if the user is an admin.
    """
    if user is None:
        return False

    # Check 1: is_superuser flag on User model
    if getattr(user, "is_superuser", False):
        return True

    # Check 2: member_id in ADMIN_MEMBER_IDS config
    member_id = getattr(user, "id", None) or getattr(user, "member_id", None)
    if member_id is not None:
        admin_ids = _get_admin_ids_from_config()
        if member_id in admin_ids:
            return True

    # Check 3: single-user mode (no multi-tenant, first user = admin)
    try:
        from app.core.config import settings
        if not settings.MULTI_TENANT_MODE:
            return True
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.debug("Suppressed error: %s", e, exc_info=True)

    return False
