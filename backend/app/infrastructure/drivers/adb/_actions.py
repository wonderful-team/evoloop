import logging
import subprocess
import time

from app.infrastructure.drivers.adb._exceptions import ADBError

logger = logging.getLogger(__name__)


class ActionMixin:
    def tap(self, x, y, device_id=None):
        self._run_adb(["shell", "input", "tap", str(x), str(y)], device_id=device_id)
        logger.info(f"Tapped at ({x}, {y})")

    def long_press(self, x, y, duration_ms=1000, device_id=None):
        self._run_adb(
            [
                "shell",
                "input",
                "swipe",
                str(x),
                str(y),
                str(x),
                str(y),
                str(duration_ms),
            ],
            device_id=device_id,
        )
        logger.info(f"Long-pressed at ({x}, {y}) for {duration_ms}ms")

    def swipe(self, x1, y1, x2, y2, duration_ms=300, device_id=None):
        self._run_adb(
            [
                "shell",
                "input",
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(duration_ms),
            ],
            device_id=device_id,
        )
        logger.info(f"Swiped from ({x1}, {y1}) to ({x2}, {y2})")

    def input_text(self, text, device_id=None):
        start = time.time()
        is_ascii = all(ord(c) < 128 for c in text)

        def _try_paste_fallback():
            logger.info(f"Using clipboard/paste fallback for text: '{text[:10]}...'")
            if self.set_clipboard(text, device_id=device_id):
                time.sleep(0.5)
                try:
                    self.press_key(279, device_id=device_id)
                except (subprocess.CalledProcessError, ADBError):
                    self._run_adb(
                        ["shell", "input", "keyevent", "--longpress", "279"],
                        device_id=device_id,
                    )
                return True
            return False

        try:
            self._run_adb(
                [
                    "shell",
                    "am",
                    "broadcast",
                    "-a",
                    "ADB_INPUT_TEXT",
                    "--es",
                    "msg",
                    f"'{text}'",
                ],
                device_id=device_id,
            )
        except (subprocess.CalledProcessError, ADBError):
            pass

        if is_ascii:
            processed_text = text.replace(" ", "%s")
            try:
                self._run_adb(
                    ["shell", "input", "text", processed_text], device_id=device_id
                )
                logger.info(
                    f"Input text '{text[:10]}...' in {(time.time() - start) * 1000:.0f}ms"
                )
                return
            except Exception as e:
                logger.debug(f"ASCII input failed, trying fallback: {e}")

        if _try_paste_fallback():
            logger.info(
                f"Successfully input text via clipboard fallback in {(time.time() - start) * 1000:.0f}ms"
            )
            return

        raise ADBError(
            f"Failed to input text: '{text}'. All methods (standard, broadcast, clipboard) failed."
        )

    def press_key(self, keycode, device_id=None):
        key_names = {
            "home": 3,
            "back": 4,
            "enter": 66,
            "delete": 67,
            "menu": 82,
            "search": 84,
            "tab": 61,
            "space": 62,
            "power": 26,
            "volume_up": 24,
            "volume_down": 25,
        }
        if isinstance(keycode, str):
            keycode_lower = keycode.lower().replace("keycode_", "")
            if keycode_lower in key_names:
                keycode = key_names[keycode_lower]
            else:
                try:
                    keycode = int(keycode)
                except ValueError:
                    raise ValueError(
                        f"Unknown keycode: {keycode}. Use numeric code or: {list(key_names.keys())}"
                    )
        self._run_adb(["shell", "input", "keyevent", str(keycode)], device_id=device_id)
        logger.info(f"Pressed keycode: {keycode}")

    def launch_app(self, package_name, device_id=None):
        self._run_adb(
            [
                "shell",
                "monkey",
                "-p",
                package_name,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            device_id=device_id,
        )

    def force_stop(self, package_name, device_id=None):
        self._run_adb(["shell", "am", "force-stop", package_name], device_id=device_id)

    def push(self, local_path, remote_path, device_id=None):
        self._run_adb(["push", local_path, remote_path], device_id=device_id)

    def pull(self, remote_path, local_path, device_id=None):
        self._run_adb(["pull", remote_path, local_path], device_id=device_id)
