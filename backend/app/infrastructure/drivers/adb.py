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
from typing import Any, Literal

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
        self._app_cache = {}  # {device_id: (timestamp, app_data)}
        self._cache_ttl = 1.5  # seconds

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
        purpose: Literal["temp", "atlas", "debug", "dataset"] = "temp",
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
        Advanced version: supports non-ASCII (Chinese) by falling back to clipboard + paste.
        """
        start = time.time()
        is_ascii = all(ord(c) < 128 for c in text)
        
        # Helper to try paste fallback (Synchronous)
        def _try_paste_fallback():
            logger.info(f"Using clipboard/paste fallback for text: '{text[:10]}...'")
            if self.set_clipboard(text, device_id=device_id):
                # Small wait for clipboard to propagate
                time.sleep(0.5)
                # 279 is KEYCODE_PASTE (Android 9+)
                # 66 is ENTER (if needed, but usually just paste)
                try:
                    self.press_key(279, device_id=device_id)
                except:
                    # Fallback to Ctrl+V if Paste keycode is not supported
                    self._run_adb(["shell", "input", "keyevent", "--longpress", "279"], device_id=device_id)
                return True
            return False

        # 1. Attempt broadcast-based input (requires ADBKeyBoard/etc)
        try:
            self._run_adb([
                "shell", "am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", f"'{text}'"
            ], device_id=device_id)
        except:
            pass

        # 2. Attempt standard input text (if ASCII)
        if is_ascii:
            processed_text = text.replace(" ", "%s")
            try:
                self._run_adb(["shell", "input", "text", processed_text], device_id=device_id)
                logger.info(f"Input text '{text[:10]}...' in {(time.time()-start)*1000:.0f}ms")
                return
            except Exception as e:
                logger.debug(f"ASCII input failed, trying fallback: {e}")

        # 3. Non-ASCII or Failed ASCII: Clipboard + Paste Fallback
        if _try_paste_fallback():
            logger.info(f"Successfully input text via clipboard fallback in {(time.time()-start)*1000:.0f}ms")
            return

        raise ADBError(f"Failed to input text: '{text}'. All methods (standard, broadcast, clipboard) failed.")

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

    def set_clipboard(self, text: str, device_id: str | None = None) -> bool:
        """
        Set the current clipboard text on the device.
        Tries multiple methods (broadcast, service call).
        """
        # Method 1: Helper broadcast (if available)
        try:
            self._run_adb([
                "shell", "am", "broadcast", "-a", "ADB_SET_CLIPBOARD", "--es", "text", f"'{text}'"
            ], device_id=device_id)
        except:
            pass

        # Method 2: Service call (Universal for Android 8-13+)
        # We try both call 2 and call 3 as indices vary by ROM
        try:
            # Note: s16 handles basic strings. Complex multi-line might fail.
            for call_idx in [2, 3]:
                # Syntax: service call clipboard [idx] i32 1 s16 "TEXT"
                # The '1' signifies USER_ID or similar in Parcel
                self._run_adb([
                    "shell", "service", "call", "clipboard", str(call_idx), "i32", "1", "s16", f'"{text}"'
                ], device_id=device_id)
            return True
        except Exception as e:
            logger.debug(f"Service call clipboard failed: {e}")

        # Method 3: am start with extra (Works on some ROMs if Settings handles it)
        try:
            self._run_adb([
                "shell", "am", "start", "-a", "android.intent.action.SEND", 
                "--es", "android.intent.extra.TEXT", f'"{text}"',
                "-t", "text/plain", "com.android.settings/.Settings"
            ], device_id=device_id)
            # This is messy as it opens a UI, so we only use as last resort or if we can close it
            return True
        except:
            pass

        return False

    def dump_ui(self, device_id: str | None = None, compressed: bool = True) -> str:
        """
        Dump the current UI hierarchy as XML.
        Robust version: tries exec-out first, then file-based with explicit verification.
        """
        start = time.time()

        # Method 1: Try direct exec-out (Fastest, avoids device filesystem issues)
        configs = [compressed, False] if compressed else [False]
        for try_compressed in configs:
            try:
                args = ["exec-out", "uiautomator", "dump"]
                if try_compressed:
                    args.append("--compressed")
                args.append("/dev/tty")

                # exec-out streams directly, no "UI hierarchy dumped to" prefix
                stdout, _ = self._run_adb(args, device_id=device_id, timeout=10)
                
                # Verify we got a valid XML block
                xml_start = stdout.find("<?xml")
                if xml_start == -1:
                    xml_start = stdout.find("<hierarchy")

                if xml_start >= 0 and "</hierarchy>" in stdout:
                    logger.info(f"Dumped UI hierarchy in {(time.time()-start)*1000:.0f}ms (exec-out, compressed={try_compressed})")
                    return stdout[xml_start:]
            except Exception as e:
                if not try_compressed:
                    logger.debug(f"exec-out dump failed: {e}")
                continue

        # Method 2: Fallback to file-based approach with explicit existence verification
        logger.warning("[ADB] exec-out dump failed, falling back to file-based dump")
        remote_path = "/data/local/tmp/window_dump.xml"
        try:
            # 1. Clean up stale file if any
            try:
                self._run_adb(["shell", "rm", "-f", remote_path], device_id=device_id)
            except:
                pass

            # 2. Try Dump
            try:
                dump_cmd = ["shell", "uiautomator", "dump"]
                if compressed:
                    dump_cmd.append("--compressed")
                dump_cmd.append(remote_path)
                self._run_adb(dump_cmd, device_id=device_id, timeout=15)
            except ADBError:
                # 3. Final fallback: standard dump
                self._run_adb(["shell", "uiautomator", "dump", remote_path], device_id=device_id, timeout=15)

            # 4. CRITICAL: Verify file existence and non-zero size
            # This addresses the "silent failure" where uiautomator exits 0 but creates no file
            try:
                self._run_adb(["shell", "test", "-s", remote_path], device_id=device_id)
            except ADBError:
                time.sleep(1.0) # Grace period
                try:
                    self._run_adb(["shell", "test", "-s", remote_path], device_id=device_id)
                except ADBError:
                    raise ADBError(f"uiautomator dump reported success but file '{remote_path}' was not created or is empty. Device UI service might be unresponsive.")

            # 5. Read and Cleanup
            stdout, _ = self._run_adb(["shell", "cat", remote_path], device_id=device_id)

            subprocess.Popen(
                [self._adb_path] + (["-s", device_id] if device_id else []) + ["shell", "rm", "-f", remote_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            logger.info(f"Dumped UI hierarchy in {(time.time()-start)*1000:.0f}ms (file)")
            return stdout
        except Exception as e:
            logger.error(f"UI hierarchy dump failed: {e}")
            raise ADBError(f"Failed to capture UI hierarchy: {e}")

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
        Robust version with multi-strategy validation and short-lived caching.
        """
        now = time.time()
        # Use a stable key for "default" device
        cache_key = device_id or "default"

        if cache_key in self._app_cache:
            ts, data = self._app_cache[cache_key]
            if now - ts < self._cache_ttl:
                return data

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
            try:
                stdout, _ = self._run_adb(["shell", "dumpsys", "activity", "top"], device_id=device_id, timeout=3)
                for line in stdout.splitlines():
                    if "ACTIVITY" in line and "/" in line:
                        parsed = parse_package_from_line(line, r'ACTIVITY\s+([\w\.]+)/([\w\.\$]+)')
                        if parsed:
                            pkg, act = parsed
                            if not is_system_package(pkg):
                                results.append((pkg, act, "top", 3))
                            break
            except Exception:
                pass

            # Strategy 2: dumpsys activity activities (mResumedActivity)
            if not results:
                try:
                    stdout, _ = self._run_adb(["shell", "dumpsys", "activity", "activities"], device_id=device_id, timeout=3)
                    for line in stdout.splitlines():
                        if ("mResumedActivity" in line or "topResumedActivity" in line) and "/" in line:
                            parsed = parse_package_from_line(line, r'([\w\.]+)/([\w\.\$]+)')
                            if parsed:
                                pkg, act = parsed
                                if not is_system_package(pkg):
                                    results.append((pkg, act, "resumed", 2))
                                break
                except Exception:
                    pass

            # Strategy 3: dumpsys window (mCurrentFocus)
            if not results:
                try:
                    stdout, _ = self._run_adb(["shell", "dumpsys", "window", "windows"], device_id=device_id, timeout=3)
                    for line in stdout.splitlines():
                        if ("mCurrentFocus" in line or "mFocusedApp" in line) and "/" in line:
                            parsed = parse_package_from_line(line, r'([\w\.]+)/([\w\.\$]+)')
                            if parsed:
                                pkg, act = parsed
                                if not is_system_package(pkg):
                                    results.append((pkg, act, "focus", 1))
                                break
                except Exception:
                    pass

            final_data = {"package": "unknown", "activity": "unknown", "confidence": "none"}

            if results:
                # Weighted vote (prefer top activity)
                packages = [r[0] for r in results]
                if len(set(packages)) == 1:
                    final_data = {
                        "package": results[0][0],
                        "activity": results[0][1],
                        "confidence": "high",
                        "source": ",".join([r[2] for r in results])
                    }
                else:
                    pkg_weights = {}
                    for pkg, act, source, weight in results:
                        pkg_weights[pkg] = pkg_weights.get(pkg, 0) + weight
                    best_pkg = max(pkg_weights.keys(), key=lambda p: pkg_weights[p])
                    best_act = next(r[1] for r in results if r[0] == best_pkg)
                    final_data = {
                        "package": best_pkg,
                        "activity": best_act,
                        "confidence": "medium",
                        "source": ",".join([r[2] for r in results if r[0] == best_pkg])
                    }

            # Update cache
            self._app_cache[cache_key] = (now, final_data)
            return final_data

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
            info: dict[str, Any] = {"package": package}
            
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
        r"""
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
