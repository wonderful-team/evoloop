"""
[DEPRECATED] — This file is a compatibility stub.

The Device Watcher has been moved to:
  app.core.environment.controllers.device_watcher

Please update all imports to use the new location.
"""
# Backward-compatible re-export
from app.core.environment.controllers.device_watcher import DeviceWatcher, device_watcher  # noqa: F401

__all__ = ["DeviceWatcher", "device_watcher"]
