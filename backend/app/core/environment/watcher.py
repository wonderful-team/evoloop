"""
Environment Watcher - DEPRECATED

This module is deprecated. Environment monitoring is now handled by:
- DeviceWatcher: Real-time Android device detection (adb track-devices)
- Network status: Detected on-demand during awaken() and tool failures

The periodic polling approach has been removed to reduce log noise and resource usage.
Network connectivity changes are infrequent enough that on-demand detection is sufficient.

For backward compatibility, the EnvironmentWatcher class remains but does nothing.
"""

import logging

logger = logging.getLogger(__name__)


class EnvironmentWatcher:
    """
    DEPRECATED: No longer used.
    
    Device detection is handled by DeviceWatcher (real-time via adb track-devices).
    Network status is detected on-demand during agent awakening and when network
    operations fail.
    """

    def __init__(self, refresh_interval: int = 300):
        """Deprecated - no-op initialization."""
        pass

    async def start(self):
        """Deprecated - no-op."""
        logger.debug("EnvironmentWatcher.start() called (deprecated, no-op)")

    async def stop(self):
        """Deprecated - no-op."""
        logger.debug("EnvironmentWatcher.stop() called (deprecated, no-op)")


# Global instance kept for backward compatibility
environment_watcher = EnvironmentWatcher()
