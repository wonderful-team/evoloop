"""
Local device identity — hostname, device name, fingerprint, OS info.

The identity of the machine running this Agent, consumed by EvoCloud device
registration, mDNS discovery and cloud sync. This is distinct from
``app.core.environment``, which tracks the mobile / embedded devices the
Agent *controls* (e.g. Android devices via ADB).

Raw OS probing is delegated to ``app.infrastructure.drivers.system``.
"""

import logging

from app.core.file import compute_sha256
from app.infrastructure.drivers.system import (
    get_hostname as _get_system_hostname,
)
from app.infrastructure.drivers.system import (
    get_os_platform as _get_system_os_platform,
)

logger = logging.getLogger(__name__)


def get_hostname() -> str:
    """Return the local machine hostname, or ``""`` if unavailable."""
    return _get_system_hostname()


def get_os_info() -> str:
    """Return a ``platform.platform()`` string describing the local OS."""
    return _get_system_os_platform()


def get_device_name() -> str:
    """Resolve the EvoLoop device display name.

    Resolution order: runtime config store (``EVOCLOUD_DEVICE_NAME``) ->
    env/settings -> hostname -> default.
    """
    from app.core.config import settings
    from app.infrastructure.config.service import SystemConfigService

    return (
        SystemConfigService.get_value("EVOCLOUD_DEVICE_NAME")
        or settings.EVOCLOUD_DEVICE_NAME
        or get_hostname()
        or "EvoLoop-Desktop"
    )


def get_device_description() -> str:
    """Resolve the EvoLoop device description."""
    from app.core.config import settings
    from app.infrastructure.config.service import SystemConfigService

    return (
        SystemConfigService.get_value("EVOCLOUD_DEVICE_DESCRIPTION")
        or settings.EVOCLOUD_DEVICE_DESCRIPTION
        or ""
    )


def get_hardware_fingerprint() -> str:
    """Get a stable hardware fingerprint for the current machine.

    Falls back gracefully if platform-specific APIs are unavailable.
    """
    from app.infrastructure.drivers.system import get_machine_id

    try:
        raw = get_machine_id()
    except Exception as e:
        logger.warning(f"Failed to get hardware fingerprint: {e}", exc_info=True)
        raw = ""

    normalized = raw.strip().lower()
    return compute_sha256(normalized)[:32]
