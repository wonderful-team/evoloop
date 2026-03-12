"""
ADB Driver - Low-level operations for Android device control.
Uses the Android Debug Bridge (adb) command-line tool.
"""

import logging
import os
import re
import subprocess
import tempfile
import time
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

        # Try to resolve device_id from Context if not provided
        if not device_id:
            try:
                from app.core.context.manager import ContextManager
                ctx_env = ContextManager.get_var("_env", {})
                devices = ctx_env.get("devices", [])
                if devices and len(devices) == 1:
                    device_id = devices[0]
            except Exception:
                pass

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

    def screenshot(
        self,
        device_id: str | None = None,
        purpose: str = "temp",
        bundle_id: str | None = None,
        suffix: str | None = None
    ) -> str:
        """
        Capture a screenshot from the device.

        Args:
            device_id: Optional device serial
            purpose: Storage purpose ("temp", "atlas", "debug", "dataset")
            bundle_id: App identifier for organization
            suffix: Additional identifier

        Returns:
            Path to the saved screenshot PNG file.
        """
        # Use hierarchical storage if available, fallback to temp
        try:
            from app.core.vision.storage import screenshot_storage
            filepath = screenshot_storage.get_path(
                purpose=purpose,
                platform="android",
                bundle_id=bundle_id,
                suffix=suffix
            )
        except Exception as e:
            logger.warning(f"[ADB] Failed to use hierarchical storage: {e}, using temp")
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

    def long_press(self, x: int, y: int, duration_ms: int = 1000, device_id: str | None = None) -> None:
        """
        Long-press at the specified coordinates using swipe with zero distance.
        """
        self._run_adb(
            ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)],
            device_id=device_id
        )
        logger.info(f"Long-pressed at ({x}, {y}) for {duration_ms}ms")

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
        Note: Standard ADB input text doesn't support non-ASCII well and can NPE on some ROMs.
        """
        start = time.time()
        
        # 1. Attempt broadcast-based input (requires ADBKeyBoard/Yosemite/etc, common in silky automation)
        # This is non-blocking and safe even if no receiver exists (just does nothing)
        try:
            self._run_adb([
                "shell", "am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", f"'{text}'"
            ], device_id=device_id)
        except:
            pass

        # 2. Attempt standard input text for ASCII/compatibility
        # We handle spaces with %s and use quotes to protect other chars
        # But for Chinese, we try a safer quoting or direct pass
        is_ascii = all(ord(c) < 128 for c in text)
        processed_text = text.replace(" ", "%s")
        
        try:
            # Wrap in double quotes for better shell compatibility in modern Android
            # If it contains complex chars, we use a single-quoted block but escape internal ones
            if is_ascii:
                self._run_adb(["shell", "input", "text", processed_text], device_id=device_id)
            else:
                # Experimental: try double-quoting for Chinese
                self._run_adb(["shell", "input", "text", f'"{processed_text}"'], device_id=device_id)
            
            logger.info(f"Input text '{text[:10]}...' in {(time.time()-start)*1000:.0f}ms")
        except ADBError as e:
            if "NullPointerException" in str(e):
                logger.warning(f"ADB 'input text' NPE detected for '{text}'. The device ROM doesn't support native non-ASCII input via standard ADB.")
                raise RuntimeError(f"Failed to input text: '{text}'. Device ROM rejected the non-ASCII characters. Consider using clipboard/paste strategy if possible, or stick to English.")
            else:
                raise e

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

    def force_stop(self, package_name: str, device_id: str | None = None) -> None:
        """
        Force-stop an application.
        """
        self._run_adb(["shell", "am", "force-stop", package_name], device_id=device_id)
        logger.info(f"Force-stopped app: {package_name}")

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

    def get_clipboard(self, device_id: str | None = None) -> str:
        """
        Get the current clipboard text from the device.
        Note: Requires ADB connection and might be restricted on modern Android.
        Attempts to use 'service call clipboard 2' which is common on many ROMs.
        """
        try:
            # Different Android versions use different service call signatures
            # This is a common one for reading clipboard (getPrimaryClip)
            stdout, _ = self._run_adb(["shell", "service", "call", "clipboard", "2", "i32", "1"], device_id=device_id)
            
            # Output format: "Result: Parcel(00000000 00000018 'https://x.y.z' ...)"
            # We extract the string within single quotes
            match = re.search(r"'(.*?)'", stdout)
            if match:
                return match.group(1).encode('utf-8').decode('unicode_escape', errors='ignore')
            
            # Alternative: Logcat fallback if the system logs clipboard changes
            return ""
        except Exception as e:
            logger.debug(f"Failed to read clipboard: {e}")
            return ""

    def dump_ui(self, device_id: str | None = None) -> str:
        """
        Dump the current UI hierarchy as XML.
        Uses --compressed to bypass 'idle state' issues common on real devices.
        """
        import time
        start = time.time()

        # Method 1: Try direct exec-out with --compressed (fastest)
        cmd = [self._adb_path]
        if device_id:
            cmd.extend(["-s", device_id])

        # Use /dev/tty as output to get direct streaming
        # Some devices support this, some don't
        try:
            # Note: Not all devices support --compressed for dump, but it's worth a try 
            # as it solves the "could not get idle state" error.
            # We try with --compressed first.
            result = subprocess.run(
                cmd + ["exec-out", "uiautomator", "dump", "--compressed", "/dev/tty"],
                capture_output=True,
                text=True,
                timeout=10
            )

            # If it failed or returns empty, try without --compressed
            if result.returncode != 0 or not result.stdout.strip():
                 result = subprocess.run(
                    cmd + ["exec-out", "uiautomator", "dump", "/dev/tty"],
                    capture_output=True,
                    text=True,
                    timeout=10
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
            logger.debug(f"exec-out method failed: {e}")

        # Method 2: Fallback to file-based approach with --compressed
        remote_path = "/data/local/tmp/window_dump.xml"
        try:
            # Try with --compressed first to avoid "idle" error
            self._run_adb(["shell", "uiautomator", "dump", "--compressed", remote_path], device_id=device_id)
        except ADBError:
            # Final fallback: standard dump
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

    def get_uptime(self, device_id: str | None = None) -> float:
        """
        Get the device's kernel uptime in seconds.
        Useful for synchronizing host time with Android kernel timestamps.
        """
        stdout, _ = self._run_adb(["shell", "cat", "/proc/uptime"], device_id=device_id)
        # Format: "uptime_seconds idle_seconds"
        try:
            return float(stdout.split()[0])
        except (IndexError, ValueError):
            logger.error(f"Failed to parse uptime from: {stdout}")
            return 0.0

    def get_current_app(self, device_id: str | None = None) -> dict:
        """
        Get the currently focused application package and activity.
        Robust version with multi-strategy validation to avoid system UI false positives.
        """
        def is_system_package(pkg: str) -> bool:
            """Check if package is system UI that should be filtered out."""
            if not pkg:
                return True
            system_prefixes = (
                "com.android.systemui",
                "com.android.launcher",
                "com.google.android.inputmethod",
                "android",
            )
            return pkg.startswith(system_prefixes) or pkg in ("unknown", "error", "")

        def parse_package_from_line(line: str, pattern: str) -> tuple[str, str] | None:
            """Extract package and activity from a line using regex pattern."""
            match = re.search(pattern, line)
            if match:
                return match.group(1), match.group(2)
            return None

        try:
            results = []

            # Strategy 1: dumpsys activity top (Most reliable for foreground app)
            # This shows the actual top activity stack, less affected by system overlays
            try:
                stdout, _ = self._run_adb(["shell", "dumpsys", "activity", "top"], device_id=device_id, timeout=5)
                for line in stdout.splitlines():
                    if "ACTIVITY" in line and "/" in line:
                        # ACTIVITY com.android.settings/.Settings u0
                        parsed = parse_package_from_line(line, r'ACTIVITY\s+([\w\.]+)/([\w\.\$]+)')
                        if parsed:
                            pkg, act = parsed
                            if not is_system_package(pkg):
                                results.append((pkg, act, "top", 3))  # weight 3
                            break  # Only take first (topmost) activity
            except Exception as e:
                logger.debug(f"Strategy 1 (top) failed: {e}")

            # Strategy 2: dumpsys activity activities (mResumedActivity)
            try:
                stdout, _ = self._run_adb(["shell", "dumpsys", "activity", "activities"], device_id=device_id)
                for line in stdout.splitlines():
                    if ("mResumedActivity" in line or "topResumedActivity" in line) and "/" in line:
                        parsed = parse_package_from_line(line, r'([\w\.]+)/([\w\.\$]+)')
                        if parsed:
                            pkg, act = parsed
                            if not is_system_package(pkg):
                                results.append((pkg, act, "resumed", 2))  # weight 2
                            break
            except Exception as e:
                logger.debug(f"Strategy 2 (resumed) failed: {e}")

            # Strategy 3: dumpsys window (mCurrentFocus)
            try:
                stdout, _ = self._run_adb(["shell", "dumpsys", "window", "windows"], device_id=device_id)
                for line in stdout.splitlines():
                    if ("mCurrentFocus" in line or "mFocusedApp" in line) and "/" in line:
                        parsed = parse_package_from_line(line, r'([\w\.]+)/([\w\.\$]+)')
                        if parsed:
                            pkg, act = parsed
                            if not is_system_package(pkg):
                                results.append((pkg, act, "focus", 1))  # weight 1
                            break
            except Exception as e:
                logger.debug(f"Strategy 3 (focus) failed: {e}")

            # Vote for the most likely package
            if not results:
                return {"package": "unknown", "activity": "unknown", "confidence": "none"}

            # If all strategies agree, high confidence
            packages = [r[0] for r in results]
            if len(set(packages)) == 1:
                return {
                    "package": results[0][0],
                    "activity": results[0][1],
                    "confidence": "high",
                    "source": ",".join([r[2] for r in results])
                }

            # Weighted vote (prefer top activity)
            pkg_weights = {}
            for pkg, act, source, weight in results:
                pkg_weights[pkg] = pkg_weights.get(pkg, 0) + weight

            best_pkg = max(pkg_weights.keys(), key=lambda p: pkg_weights[p])
            best_act = next(r[1] for r in results if r[0] == best_pkg)

            return {
                "package": best_pkg,
                "activity": best_act,
                "confidence": "medium",
                "source": ",".join([r[2] for r in results if r[0] == best_pkg]),
                "alternatives": list(set(packages))
            }

        except Exception as e:
            logger.error(f"Failed to get current Android app: {e}")
            return {"package": "error", "activity": "error", "confidence": "none"}

    def get_package_info(self, package: str, device_id: str | None = None) -> dict:
        """
        Get metadata about an installed package (versionCode, versionName, lastUpdateTime).
        Used for version drift detection in App Atlas.
        """
        try:
            stdout, _ = self._run_adb(["shell", "dumpsys", "package", package], device_id=device_id, timeout=10)
            info = {"package": package}
            
            # Extract versionCode
            vc_match = re.search(r'versionCode=(\d+)', stdout)
            if vc_match:
                info["version_code"] = int(vc_match.group(1))
            
            # Extract versionName
            vn_match = re.search(r'versionName=([\d\.\w\-]+)', stdout)
            if vn_match:
                info["version_name"] = vn_match.group(1).strip()
                
            # Extract lastUpdateTime
            lut_match = re.search(r'lastUpdateTime=([\d\-: ]+)', stdout)
            if lut_match:
                info["last_update_time"] = lut_match.group(1).strip()
                
            return info
        except Exception as e:
            logger.error(f"Failed to get package info for {package}: {e}")
            return {"package": package, "error": str(e)}

    def check_app_status(self, package: str, device_id: str | None = None) -> str:
        """
        Check if an app is running, crashed, or showing an ANR.
        Returns: 'foreground', 'background', 'crashed', 'not_installed', 'unknown'
        """
        try:
            # Check if package is installed
            stdout, _ = self._run_adb(["shell", "pm", "path", package], device_id=device_id, timeout=5)
            if not stdout.strip():
                return "not_installed"

            # Check if foreground
            curr = self.get_current_app(device_id=device_id)
            if curr.get("package") == package:
                return "foreground"

            # Check for crash dialogs in window list
            stdout, _ = self._run_adb(["shell", "dumpsys", "window", "windows"], device_id=device_id, timeout=10)
            if "Application Error:" in stdout or "Application Not Responding:" in stdout:
                if package in stdout:
                    return "crashed"

            # Check if running at all
            try:
                stdout, _ = self._run_adb(["shell", "pidof", package], device_id=device_id, timeout=5)
                if stdout.strip():
                    return "background"
            except: pass

            return "unknown"
        except Exception:
            return "unknown"

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

    def read_sms(
        self,
        regex_pattern: str | None = None,
        timeout: int = 30,
        device_id: str | None = None,
        after_timestamp: int | None = None,
    ) -> list[dict]:
        """
        Read recent SMS messages from the device inbox.
        If a regex_pattern is provided, polls for up to timeout seconds until a match is found.

        Polling Strategy:
        - Waits 3 seconds before first query (SMS typically takes 3-8s to arrive)
        - Then polls with dynamic intervals: 2s → 2s → 3s → 3s → 3s → 5s → 5s...
        - Returns immediately when a matching SMS is found
        - Returns empty list if timeout is reached without finding a match

        Args:
            regex_pattern: Optional regex to match against message bodies (e.g., r'\d{4,6}').
            timeout: Maximum seconds to poll if regex_pattern is provided.
            device_id: Optional device serial
            after_timestamp: Optional Unix timestamp (milliseconds). Only return SMS with date > this value.
                            Use this to filter out old messages and only listen for new ones.

        Returns:
            List of matching SMS dicts with 'body', 'date', and 'extract' keys.
        """
        start_time = time.time()

        # Phase 1: Initial delay - SMS typically takes 3-8 seconds to arrive
        # Skip initial query to avoid false negatives on recently sent codes
        initial_delay = min(3, timeout)  # Wait at least 3 seconds before first query, or less if timeout is short
        if initial_delay > 0:
            time.sleep(initial_delay)

        # Phase 2: Polling loop with dynamic intervals
        poll_count = 0
        base_interval = 2.0  # Base polling interval in seconds

        while True:
            try:
                # Query the latest 5 messages
                cmd = ["shell", "content", "query", "--uri", "content://sms/inbox", "--projection", "body,date"]
                stdout_str, _ = self._run_adb(cmd, device_id=device_id)
                
                messages = []
                for line in stdout_str.splitlines():
                    if not line.startswith("Row:"):
                        continue
                        
                    # Parse: Row: X body=Some text, date=1680581222876
                    body_match = re.search(r'body=(.*?), date=', line)
                    date_match = re.search(r'date=(\d+)', line)
                    
                    if body_match and date_match:
                        body_text = body_match.group(1).strip()
                        date_val = int(date_match.group(1))

                        # Skip messages older than after_timestamp (if specified)
                        if after_timestamp and date_val <= after_timestamp:
                            continue

                        msg_dict = {"body": body_text, "date": date_val, "extract": None}

                        if regex_pattern:
                            extract_match = re.search(regex_pattern, body_text)
                            if extract_match:
                                msg_dict["extract"] = extract_match.group(0)
                                messages.append(msg_dict)
                        else:
                            messages.append(msg_dict)
                
                # If we are looking for a specific pattern and found it, return immediately
                if regex_pattern and len(messages) > 0:
                    # Sort by date descending (newest first)
                    messages.sort(key=lambda x: x["date"], reverse=True)
                    return messages
                
                # If we are not polling for a pattern, just return the raw messages
                if not regex_pattern:
                    messages.sort(key=lambda x: x["date"], reverse=True)
                    return messages
                    
            except Exception as e:
                logger.warning(f"Failed to read SMS: {e}")

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                break

            # Dynamic polling interval: more frequent at first, then slower
            poll_count += 1
            if poll_count <= 2:
                sleep_interval = 2.0  # First 2 polls: every 2 seconds
            elif poll_count <= 5:
                sleep_interval = 3.0  # Next 3 polls: every 3 seconds
            else:
                sleep_interval = 5.0  # After that: every 5 seconds

            # Don't sleep longer than remaining timeout
            remaining = timeout - elapsed
            sleep_interval = min(sleep_interval, remaining)
            if sleep_interval > 0:
                time.sleep(sleep_interval)

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
