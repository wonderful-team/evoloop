"""
MacOS Driver - Low-level operations for desktop control.
Uses native MacOS commands: screencapture, osascript, open.
"""

import logging

from app.infrastructure.drivers.macos.actions import ActionsMixin
from app.infrastructure.drivers.macos.apps import AppMixin
from app.infrastructure.drivers.macos.ax import AXMixin
from app.infrastructure.drivers.macos.info import InfoMixin
from app.infrastructure.drivers.macos.screenshot import ScreenshotMixin

logger = logging.getLogger(__name__)


class MacOSDriver(
    ScreenshotMixin,
    ActionsMixin,
    AppMixin,
    AXMixin,
    InfoMixin,
):
    pass


macos_driver = MacOSDriver()
