import logging
import subprocess

from app.infrastructure.drivers.adb._exceptions import ADBError

logger = logging.getLogger(__name__)


class CoreMixin:
    def _run_adb(self, args, device_id=None, timeout=30):
        cmd = [self._adb_path]

        if not device_id:
            try:
                from app.core.context.manager import ContextManager

                ctx_env = ContextManager.get_var("_env", {})
                devices = ctx_env.get("devices", [])
                if devices and len(devices) == 1:
                    device_id = devices[0]
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        if device_id:
            cmd.extend(["-s", device_id])
        cmd.extend(args)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                if "device not found" in result.stderr.lower():
                    raise ADBError("No Android device connected. Please connect via USB and enable USB Debugging.")
                if "more than one device" in result.stderr.lower():
                    raise ADBError("Multiple devices connected. Please specify device_id.")
                if "unauthorized" in result.stderr.lower():
                    raise ADBError("Device is unauthorized. Please accept the USB debugging prompt on your device.")
                raise ADBError(f"ADB command failed: {result.stderr}")
            return result.stdout, result.stderr
        except FileNotFoundError:
            raise ADBError(
                "ADB not found. Please install Android SDK Platform Tools:\n"
                "  brew install android-platform-tools"
            )
        except subprocess.TimeoutExpired:
            raise ADBError(f"ADB command timed out after {timeout}s")

    def list_devices(self):
        stdout, _ = self._run_adb(["devices", "-l"])
        devices = []
        for line in stdout.strip().split("\n")[1:]:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                devices.append({
                    "serial": parts[0],
                    "status": parts[1],
                    "info": " ".join(parts[2:]) if len(parts) > 2 else "",
                })
        return devices

    def check_uiautomator2_available(self, device_id=None):
        try:
            import uiautomator2 as u2

            d = u2.connect(device_id) if device_id else u2.connect()
            d.info
            return True
        except Exception:
            return False

    def install_uiautomator2(self, device_id=None):
        try:
            import uiautomator2 as u2

            u2.connect(device_id) if device_id else u2.connect()
            return True
        except Exception:
            pass
        try:
            from app.core.context.manager import ContextManager

            device_id_val = device_id or ContextManager.get_var("device_id")
            stdout, stderr = subprocess.Popen(
                ["python3", "-m", "uiautomator2", "init"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).communicate(timeout=30)
            output = (stdout + stderr).decode().lower()
            return "success" in output
        except Exception as e:
            logger.warning(f"uiautomator2 install failed: {e}")
            return False

    def ensure_uiautomator2(self, device_id=None, auto_install=True):
        if self.check_uiautomator2_available(device_id):
            return True
        if auto_install:
            return self.install_uiautomator2(device_id)
        return False

    def detect_device_capabilities(self, device_id):
        logger.info(f"[ADB] Detecting capabilities for device {device_id}...")
        capabilities = {"native_uiautomator": True, "uiautomator2": False}

        try:
            stdout, stderr = self._run_adb(
                ["shell", "uiautomator", "dump", "/dev/null"],
                device_id=device_id,
                timeout=5,
            )
            output = (stdout + stderr).lower()
            if "idle" in output or "could not get" in output:
                capabilities["native_uiautomator"] = False
                logger.info(f"[ADB] Device {device_id}: Native uiautomator NOT working (idle state error)")
            else:
                logger.info(f"[ADB] Device {device_id}: Native uiautomator OK")
        except Exception as e:
            capabilities["native_uiautomator"] = False
            logger.info(f"[ADB] Device {device_id}: Native uiautomator NOT working ({e})")

        if self.check_uiautomator2_available(device_id):
            capabilities["uiautomator2"] = True
            logger.info(f"[ADB] Device {device_id}: uiautomator2 OK")
        elif not capabilities["native_uiautomator"]:
            logger.info(f"[ADB] Device {device_id}: Native uiautomator broken, auto-installing uiautomator2...")
            if self.ensure_uiautomator2(device_id, auto_install=True):
                capabilities["uiautomator2"] = True
                logger.info(f"[ADB] Device {device_id}: uiautomator2 installed successfully")
            else:
                logger.error(f"[ADB] Device {device_id}: Failed to install uiautomator2")
        else:
            logger.info(f"[ADB] Device {device_id}: uiautomator2 NOT available")

        self._device_capabilities[device_id] = capabilities
        if capabilities["uiautomator2"]:
            logger.info(f"[ADB] Device {device_id}: Will use uiautomator2 (optimal)")
        elif capabilities["native_uiautomator"]:
            logger.info(f"[ADB] Device {device_id}: Will use native uiautomator")
        else:
            logger.warning(f"[ADB] Device {device_id}: No working UI automation method!")
        return capabilities
