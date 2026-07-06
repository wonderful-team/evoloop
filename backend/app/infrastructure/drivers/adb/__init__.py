import logging
import os
import subprocess

from app.infrastructure.drivers.adb._exceptions import ADBError
from app.infrastructure.drivers.adb._info import DeviceInfoMixin
from app.infrastructure.drivers.adb._actions import ActionMixin
from app.infrastructure.drivers.adb._core import CoreMixin
from app.infrastructure.drivers.adb._ui import UIMixin
from app.infrastructure.drivers.adb._clipboard import ClipboardMixin
from app.infrastructure.drivers.adb._sms import SMSMixin

logger = logging.getLogger(__name__)


class ADBDriver(
    CoreMixin,
    ActionMixin,
    UIMixin,
    DeviceInfoMixin,
    ClipboardMixin,
    SMSMixin,
):
    def __init__(self):
        self._adb_path = self._find_adb()
        self._dump_lock = __import__("threading").Lock()
        self._app_cache = {}
        self._cache_ttl = 1.5
        self._device_capabilities = {}

    def _find_adb(self) -> str:
        paths = [
            "/opt/homebrew/bin/adb",
            "/usr/local/bin/adb",
            os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
            os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        result = subprocess.run(["which", "adb"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "adb"

    def is_available(self) -> bool:
        try:
            devices = self.list_devices()
            return any(d["status"] == "device" for d in devices)
        except ADBError:
            return False


adb_driver = ADBDriver()
