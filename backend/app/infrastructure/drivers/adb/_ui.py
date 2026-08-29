import logging
import os
import subprocess
import tempfile
import time

from app.infrastructure.drivers.adb._exceptions import ADBError
from app.utils.id import gen_uuid_hex, stamped_id
from app.utils.time import elapsed_ms

logger = logging.getLogger(__name__)


class UIMixin:
    def screenshot(self, device_id=None, purpose="temp", bundle_id=None, suffix=None):
        try:
            from app.infrastructure.vision.storage import screenshot_storage

            filepath = screenshot_storage.get_path(
                purpose=purpose,
                platform="android",
                bundle_id=bundle_id,
                suffix=suffix
            )
        except Exception as e:
            logger.warning(f"[ADB] Failed to use hierarchical storage: {e}, using temp", exc_info=True)
            timestamp = stamped_id()
            filename = f"android_screenshot_{timestamp}.png"
            filepath = os.path.join(tempfile.gettempdir(), filename)

        cmd = [self._adb_path]
        if device_id:
            cmd.extend(["-s", device_id])
        cmd.extend(["exec-out", "screencap", "-p"])

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            if result.returncode != 0:
                raise ADBError(f"Screenshot failed: {result.stderr.decode()}")
            with open(filepath, "wb") as f:
                f.write(result.stdout)
            logger.info(f"Android screenshot saved: {filepath}")
            return filepath
        except subprocess.TimeoutExpired:
            raise ADBError("Screenshot timed out")

    def dump_ui(self, device_id=None, compressed=True):
        with self._dump_lock:
            start = time.time()

            if not device_id:
                try:
                    from app.core.context.manager import ContextManager

                    ctx_env = ContextManager.get_var("_env", {})
                    devices = ctx_env.get("devices", [])
                    if devices and len(devices) == 1:
                        device_id = devices[0]
                except Exception as e:
                    logger.debug("Suppressed error: %s", e, exc_info=True)

            capabilities = self._device_capabilities.get(device_id, {})

            if capabilities.get("uiautomator2"):
                try:
                    import uiautomator2 as u2

                    d = u2.connect(device_id) if device_id else u2.connect()
                    xml_content = d.dump_hierarchy()
                    if xml_content and "<hierarchy" in xml_content:
                        logger.info(f"Dumped UI hierarchy in {elapsed_ms(start):.0f}ms (uiautomator2, cached)")
                        return xml_content
                except Exception as e:
                    logger.warning(f"[ADB] Cached uiautomator2 failed: {e}, will retry", exc_info=True)

            elif capabilities.get("native_uiautomator") and not capabilities.get("uiautomator2"):
                return self._dump_ui_native(device_id, compressed, start)

            logger.debug(f"[ADB] Unknown capabilities for {device_id}, trying uiautomator2 first...")

            try:
                import uiautomator2 as u2

                d = u2.connect(device_id) if device_id else u2.connect()
                xml_content = d.dump_hierarchy()
                if xml_content and "<hierarchy" in xml_content:
                    if device_id:
                        self._device_capabilities[device_id] = {
                            "uiautomator2": True,
                            "native_uiautomator": False,
                        }
                    logger.info(f"Dumped UI hierarchy in {elapsed_ms(start):.0f}ms (uiautomator2, auto-detected)")
                    return xml_content
            except Exception:
                logger.debug("[ADB] uiautomator2 dump failed, trying native", exc_info=True)

            logger.debug("[ADB] uiautomator2 not available, trying native...")
            try:
                return self._dump_ui_native(device_id, compressed, start)
            except Exception as native_err:
                raise ADBError(f"Failed to capture UI hierarchy. uiautomator2 not available, native: {native_err}")

    def _dump_ui_native(self, device_id, compressed, start_time):
        configs = [compressed, False] if compressed else [False]
        for try_compressed in configs:
            try:
                args = ["exec-out", "uiautomator", "dump"]
                if try_compressed:
                    args.append("--compressed")
                args.append("/dev/tty")

                stdout, _ = self._run_adb(args, device_id=device_id, timeout=10)

                xml_start = stdout.find("<?xml")
                if xml_start == -1:
                    xml_start = stdout.find("<hierarchy")

                if xml_start >= 0 and "</hierarchy>" in stdout:
                    if device_id:
                        self._device_capabilities[device_id] = {
                            "native_uiautomator": True,
                            "uiautomator2": False,
                        }
                    logger.info(f"Dumped UI hierarchy in {elapsed_ms(start_time):.0f}ms (native exec-out)")
                    return stdout[xml_start:]
            except Exception:
                continue

        unique_id = gen_uuid_hex()[:8]
        remote_path = f"/data/local/tmp/window_dump_{unique_id}.xml"
        try:
            dump_cmd = ["shell", "uiautomator", "dump"]
            if compressed:
                dump_cmd.append("--compressed")
            dump_cmd.append(remote_path)
            self._run_adb(dump_cmd, device_id=device_id, timeout=15)
            self._run_adb(["shell", "test", "-s", remote_path], device_id=device_id)

            stdout, _ = self._run_adb(["shell", "cat", remote_path], device_id=device_id)
            subprocess.Popen(
                [self._adb_path] + (["-s", device_id] if device_id else []) + ["shell", "rm", "-f", remote_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

            if device_id:
                self._device_capabilities[device_id] = {
                    "native_uiautomator": True,
                    "uiautomator2": False,
                }
            logger.info(f"Dumped UI hierarchy in {elapsed_ms(start_time):.0f}ms (native file)")
            return stdout
        except Exception as e:
            raise ADBError(f"Native uiautomator failed: {e}")
