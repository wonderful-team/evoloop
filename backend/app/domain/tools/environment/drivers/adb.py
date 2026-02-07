"""
ADB Driver - Low-level operations for Android device control.
Uses the Android Debug Bridge (adb) command-line tool.
"""

import logging
import os
import subprocess
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)


class ADBError(Exception):
    """Exception raised for ADB-related errors."""
    pass


class ADBDriver:
    """
    Low-level Android device control driver via ADB.
    All methods are synchronous and raise exceptions on failure.
    """

    def __init__(self):
        self._adb_path = self._find_adb()

    def _find_adb(self) -> str:
        """Find the adb executable path."""
        # Common locations
        paths = [
            "/opt/homebrew/bin/adb",
            "/usr/local/bin/adb",
            os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
            os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
        ]
        
        for path in paths:
            if os.path.exists(path):
                return path
        
        # Try finding in PATH
        result = subprocess.run(["which", "adb"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        
        return "adb"  # Fallback to hoping it's in PATH

    def _run_adb(self, args: list[str], device_id: str | None = None, timeout: int = 30) -> tuple[str, str]:
        """
        Run an adb command.
        
        Args:
            args: Command arguments (without 'adb' prefix)
            device_id: Optional device serial to target
            timeout: Command timeout in seconds
            
        Returns:
            Tuple of (stdout, stderr)
        """
        cmd = [self._adb_path]
        
        if device_id:
            cmd.extend(["-s", device_id])
        
        cmd.extend(args)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode != 0:
                # Check for common errors
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

    def list_devices(self) -> list[dict]:
        """
        List connected Android devices.
        
        Returns:
            List of device dicts with 'serial' and 'status' keys.
        """
        stdout, _ = self._run_adb(["devices", "-l"])
        
        devices = []
        for line in stdout.strip().split("\n")[1:]:  # Skip header
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                devices.append({
                    "serial": parts[0],
                    "status": parts[1],
                    "info": " ".join(parts[2:]) if len(parts) > 2 else ""
                })
        
        return devices

    def screenshot(self, device_id: str | None = None) -> str:
        """
        Capture a screenshot from the device.
        
        Args:
            device_id: Optional device serial
            
        Returns:
            Path to the saved screenshot PNG file.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"android_screenshot_{timestamp}.png"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        
        # Use screencap and pull in one pipeline
        # Method 1: exec-out (faster, streams directly)
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

    def tap(self, x: int, y: int, device_id: str | None = None) -> None:
        """
        Tap at the specified coordinates.
        
        Args:
            x: X coordinate
            y: Y coordinate
            device_id: Optional device serial
        """
        self._run_adb(["shell", "input", "tap", str(x), str(y)], device_id=device_id)
        logger.info(f"Tapped at ({x}, {y})")

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
        device_id: str | None = None
    ) -> None:
        """
        Swipe from (x1, y1) to (x2, y2).
        
        Args:
            x1, y1: Start coordinates
            x2, y2: End coordinates
            duration_ms: Duration in milliseconds
            device_id: Optional device serial
        """
        self._run_adb(
            ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)],
            device_id=device_id
        )
        logger.info(f"Swiped from ({x1}, {y1}) to ({x2}, {y2})")

    def input_text(self, text: str, device_id: str | None = None) -> None:
        """
        Input text to the device.
        Note: ADB doesn't support non-ASCII characters well.
        """
        # ADB input text doesn't handle spaces well - use %s instead
        # Also need to escape shell metacharacters for the 'adb shell input text' command
        # A safer way is to use single quotes around the text, but adb shell handles them differently 
        # for different OSes. The most robust simple way:
        shell_text = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"').replace("|", "\\|").replace("&", "\\&")
        
        self._run_adb(["shell", "input", "text", f"'{shell_text}'"], device_id=device_id)
        logger.info(f"Input text: {text[:20]}...")

    def press_key(self, keycode: int | str, device_id: str | None = None) -> None:
        """
        Press a key by keycode.
        
        Common keycodes:
        - HOME = 3
        - BACK = 4
        - CALL = 5
        - ENDCALL = 6
        - VOLUME_UP = 24
        - VOLUME_DOWN = 25
        - POWER = 26
        - CAMERA = 27
        - ENTER = 66
        - DEL = 67
        - MENU = 82
        
        Args:
            keycode: Android keycode (int or name like "KEYCODE_HOME")
            device_id: Optional device serial
        """
        # Handle common names
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
                    raise ValueError(f"Unknown keycode: {keycode}. Use numeric code or: {list(key_names.keys())}")
        
        self._run_adb(["shell", "input", "keyevent", str(keycode)], device_id=device_id)
        logger.info(f"Pressed keycode: {keycode}")

    def launch_app(self, package_name: str, device_id: str | None = None) -> None:
        """
        Launch an application by package name using monkey.
        Using monkey is often more robust than establishing the main activity manually.
        """
        # "monkey -p package.name -c android.intent.category.LAUNCHER 1"
        self._run_adb(
            ["shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"],
            device_id=device_id
        )
        logger.info(f"Launched app: {package_name}")

    def push(self, local_path: str, remote_path: str, device_id: str | None = None) -> None:
        """
        Push a local file or directory to the device.
        """
        self._run_adb(["push", local_path, remote_path], device_id=device_id)
        logger.info(f"Pushed {local_path} to {remote_path}")

    def pull(self, remote_path: str, local_path: str, device_id: str | None = None) -> None:
        """
        Pull a file or directory from the device to local machine.
        """
        self._run_adb(["pull", remote_path, local_path], device_id=device_id)
        logger.info(f"Pulled {remote_path} to {local_path}")

    def dump_ui(self, device_id: str | None = None) -> str:
        """
        Dump the current UI hierarchy as XML.
        
        Args:
            device_id: Optional device serial
            
        Returns:
            XML string of the UI hierarchy.
        """
        import time
        start = time.time()
        
        # Method 1: Try direct exec-out (faster, single command)
        cmd = [self._adb_path]
        if device_id:
            cmd.extend(["-s", device_id])
        
        # Use /dev/tty as output to get direct streaming
        # Some devices support this, some don't
        try:
            result = subprocess.run(
                cmd + ["exec-out", "uiautomator", "dump", "/dev/tty"],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Output format: "UI hierchary dumped to: /dev/tty\n<xml>..."
                output = result.stdout
                # Find the XML start
                xml_start = output.find("<?xml")
                if xml_start == -1:
                    xml_start = output.find("<hierarchy")
                
                if xml_start >= 0:
                    xml_content = output[xml_start:]
                    logger.info(f"Dumped UI hierarchy in {(time.time()-start)*1000:.0f}ms (exec-out)")
                    return xml_content
        except Exception as e:
            logger.debug(f"exec-out method failed: {e}, using fallback")
        
        # Method 2: Fallback to file-based approach
        remote_path = "/sdcard/window_dump.xml"
        
        self._run_adb(["shell", "uiautomator", "dump", remote_path], device_id=device_id)
        stdout, _ = self._run_adb(["shell", "cat", remote_path], device_id=device_id)
        
        # Cleanup (async, don't wait)
        subprocess.Popen(
            [self._adb_path] + (["-s", device_id] if device_id else []) + ["shell", "rm", "-f", remote_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        logger.info(f"Dumped UI hierarchy in {(time.time()-start)*1000:.0f}ms (file)")
        return stdout

    def get_screen_size(self, device_id: str | None = None) -> tuple[int, int]:
        """
        Get the device screen resolution.
        
        Returns:
            Tuple of (width, height)
        """
        stdout, _ = self._run_adb(["shell", "wm", "size"], device_id=device_id)
        
        # Parse "Physical size: 1080x2400"
        for line in stdout.strip().split("\n"):
            if "Physical size" in line or "Override size" not in line:
                try:
                    size_str = line.split(":")[-1].strip()
                    w, h = map(int, size_str.split("x"))
                    return w, h
                except (ValueError, IndexError):
                    pass
        
        # Fallback
        return 1080, 1920

    def get_system_info(self, device_id: str | None = None) -> dict:
        """
        Get Android system info.
        """
        try:
            model = self._run_adb(["shell", "getprop", "ro.product.model"], device_id=device_id)[0].strip()
            version = self._run_adb(["shell", "getprop", "ro.build.version.release"], device_id=device_id)[0].strip()
            sdk = self._run_adb(["shell", "getprop", "ro.build.version.sdk"], device_id=device_id)[0].strip()
            # Battery
            battery = self._run_adb(["shell", "dumpsys", "battery", "|", "grep", "level"], device_id=device_id)[0].strip()
            
            return {
                "model": model,
                "os_version": f"Android {version} (SDK {sdk})",
                "battery": battery.split(":")[-1].strip() + "%" if ":" in battery else "unknown",
                "platform": "android"
            }
        except Exception as e:
            return {"error": str(e)}

    def list_installed_apps(self, device_id: str | None = None) -> list[str]:
        """
        List installed application packages.
        """
        try:
            # Filter for 3rd party apps or just all
            output = self._run_adb(["shell", "pm", "list", "packages", "-3"], device_id=device_id)[0]
            packages = [line.replace("package:", "").strip() for line in output.splitlines() if line.startswith("package:")]
            return sorted(packages)
        except Exception:
            return []

    def is_available(self) -> bool:

        """
        Check if ADB is available and at least one device is connected.
        
        Returns:
            True if ready, False otherwise.
        """
        try:
            devices = self.list_devices()
            return any(d["status"] == "device" for d in devices)
        except ADBError:
            return False


# Singleton instance
adb_driver = ADBDriver()
