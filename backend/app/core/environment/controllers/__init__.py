"""
Environment Controllers — Core capability implementations.

These controllers contain the actual logic for interacting with the environment.
They are separated from the @evoloop_tool wrappers in domain/tools to allow:
  1. Direct invocation from MacroEngine without tool overhead
  2. A single source of truth for environment capabilities
  3. Clean dependency: core/environment owns the behavior,
     domain/tools exposes it to the Agent via @evoloop_tool.
"""

from app.core.environment.controllers.browser_controller import BrowserController
from app.core.environment.controllers.desktop_controller import DesktopController
from app.core.environment.controllers.mobile_controller import MobileController
from app.core.environment.controllers.device_watcher import DeviceWatcher, device_watcher
from app.core.environment.controllers.mirror_session import MirrorSession, MirrorSessionManager, mirror_manager

__all__ = [
    "BrowserController",
    "DesktopController",
    "MobileController",
    "DeviceWatcher",
    "device_watcher",
    "MirrorSession",
    "MirrorSessionManager",
    "mirror_manager",
]
