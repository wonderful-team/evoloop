import logging
import re

from app.infrastructure.drivers.adb._exceptions import ADBError

logger = logging.getLogger(__name__)


class ClipboardMixin:
    def get_clipboard(self, device_id=None):
        try:
            import uiautomator2 as u2
            d = u2.connect(device_id) if device_id else u2.connect()
            return d.clipboard
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
            pass
        try:
            from app.core.context.manager import ContextManager
            device_id_val = device_id or ContextManager.get_var("device_id")
            stdout, _ = self._run_adb(["shell", "content", "read", "--uri", "content://clipboard"], device_id=device_id_val)
            for line in stdout.splitlines():
                if "text=" in line:
                    match = re.search(r'text=(.*)', line)
                    if match:
                        return match.group(1).strip()
            return ""
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[ADB] Clipboard read failed: {e}")
            return ""

    def set_clipboard(self, text, device_id=None):
        try:
            import uiautomator2 as u2
            d = u2.connect(device_id) if device_id else u2.connect()
            d.clipboard = text
            return True
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
            pass
        try:
            escaped_text = text.replace("'", "'\\''")
            self._run_adb(
                ["shell", "am", "broadcast", "-a", "evoloop.SET_CLIPBOARD", "--es", "text", escaped_text],
                device_id=device_id,
            )
            return True
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[ADB] Clipboard write failed: {e}")
            return False
