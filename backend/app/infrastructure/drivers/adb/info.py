import logging
import re
import time

logger = logging.getLogger(__name__)


class DeviceInfoMixin:
    def get_screen_size(self, device_id=None):
        stdout, _ = self._run_adb(["shell", "wm", "size"], device_id=device_id)
        for line in stdout.strip().split("\n"):
            if "Physical size" in line or "Override size" not in line:
                try:
                    size_str = line.split(":")[-1].strip()
                    w, h = map(int, size_str.split("x"))
                    return w, h
                except (ValueError, IndexError):
                    pass
        return 1080, 1920

    def get_system_info(self, device_id=None):
        try:
            model = self._run_adb(["shell", "getprop", "ro.product.model"], device_id=device_id)[0].strip()
            version = self._run_adb(["shell", "getprop", "ro.build.version.release"], device_id=device_id)[0].strip()
            sdk = self._run_adb(["shell", "getprop", "ro.build.version.sdk"], device_id=device_id)[0].strip()
            battery = self._run_adb(["shell", "dumpsys", "battery", "|", "grep", "level"], device_id=device_id)[0].strip()
            return {
                "model": model,
                "os_version": f"Android {version} (SDK {sdk})",
                "battery": battery.split(":")[-1].strip() + "%" if ":" in battery else "unknown",
                "platform": "android",
            }
        except Exception as e:
            return {"error": str(e)}

    def get_uptime(self, device_id=None):
        stdout, _ = self._run_adb(["shell", "cat", "/proc/uptime"], device_id=device_id)
        try:
            return float(stdout.split()[0])
        except (IndexError, ValueError):
            logger.exception(f"Failed to parse uptime from: {stdout}")
            return 0.0

    def get_current_app(self, device_id=None):
        now = time.time()
        cache_key = device_id or "default"

        if cache_key in self._app_cache:
            ts, data = self._app_cache[cache_key]
            if now - ts < self._cache_ttl:
                return data

        def is_system_package(pkg):
            if not pkg:
                return True
            system_prefixes = (
                "com.android.systemui",
                "com.android.launcher",
                "com.google.android.inputmethod",
                "android",
            )
            return pkg.startswith(system_prefixes) or pkg in ("unknown", "error", "")

        def parse_package_from_line(line, pattern):
            match = re.search(pattern, line)
            if match:
                return match.group(1), match.group(2)
            return None

        try:
            results = []

            try:
                stdout, _ = self._run_adb(["shell", "dumpsys", "activity", "top"], device_id=device_id, timeout=3)
                for line in stdout.splitlines():
                    if "ACTIVITY" in line and "/" in line:
                        parsed = parse_package_from_line(line, r"ACTIVITY\s+([\w\.]+)/([\w\.\$]+)")
                        if parsed:
                            pkg, act = parsed
                            if not is_system_package(pkg):
                                results.append((pkg, act, "top", 3))
                            break
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

            if not results:
                try:
                    stdout, _ = self._run_adb(
                        ["shell", "dumpsys", "activity", "activities"],
                        device_id=device_id,
                        timeout=3,
                    )
                    for line in stdout.splitlines():
                        if ("mResumedActivity" in line or "topResumedActivity" in line) and "/" in line:
                            parsed = parse_package_from_line(line, r"([\w\.]+)/([\w\.\$]+)")
                            if parsed:
                                pkg, act = parsed
                                if not is_system_package(pkg):
                                    results.append((pkg, act, "resumed", 2))
                                break
                except Exception as e:
                    logger.debug("Suppressed error: %s", e, exc_info=True)

            if not results:
                try:
                    stdout, _ = self._run_adb(
                        ["shell", "dumpsys", "window", "windows"],
                        device_id=device_id,
                        timeout=3,
                    )
                    for line in stdout.splitlines():
                        if ("mCurrentFocus" in line or "mFocusedApp" in line) and "/" in line:
                            parsed = parse_package_from_line(line, r"([\w\.]+)/([\w\.\$]+)")
                            if parsed:
                                pkg, act = parsed
                                if not is_system_package(pkg):
                                    results.append((pkg, act, "focus", 1))
                                break
                except Exception as e:
                    logger.debug("Suppressed error: %s", e, exc_info=True)

            final_data = {
                "package": "unknown",
                "activity": "unknown",
                "confidence": 0.0,
            }

            if results:
                packages = [r[0] for r in results]
                if len(set(packages)) == 1:
                    final_data = {
                        "package": results[0][0],
                        "activity": results[0][1],
                        "confidence": 1.0,
                        "source": ",".join([r[2] for r in results]),
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
                        "confidence": 0.5,
                        "source": ",".join([r[2] for r in results if r[0] == best_pkg]),
                    }

            self._app_cache[cache_key] = (now, final_data)
            return final_data

        except Exception as e:
            logger.exception(f"Failed to get current Android app: {e}")
            return {"package": "error", "activity": "error", "confidence": "none"}

    def get_package_info(self, package, device_id=None):
        try:
            stdout, _ = self._run_adb(
                ["shell", "dumpsys", "package", package],
                device_id=device_id,
                timeout=10,
            )
            info = {"package": package}
            vc_match = re.search(r"versionCode=(\d+)", stdout)
            if vc_match:
                info["version_code"] = int(vc_match.group(1))
            vn_match = re.search(r"versionName=([\d\.\w\-]+)", stdout)
            if vn_match:
                info["version_name"] = vn_match.group(1).strip()
            lut_match = re.search(r"lastUpdateTime=([\d\-: ]+)", stdout)
            if lut_match:
                info["last_update_time"] = lut_match.group(1).strip()
            return info
        except Exception as e:
            logger.exception(f"Failed to get package info for {package}: {e}")
            return {"package": package, "error": str(e)}

    def check_app_status(self, package, device_id=None):
        try:
            stdout, _ = self._run_adb(["shell", "pm", "path", package], device_id=device_id, timeout=5)
            if not stdout.strip():
                return "not_installed"

            curr = self.get_current_app(device_id=device_id)
            if curr.get("package") == package:
                return "foreground"

            stdout, _ = self._run_adb(
                ["shell", "dumpsys", "window", "windows"],
                device_id=device_id,
                timeout=10,
            )
            if "Application Error:" in stdout or "Application Not Responding:" in stdout:
                if package in stdout:
                    return "crashed"

            try:
                stdout, _ = self._run_adb(["shell", "pidof", package], device_id=device_id, timeout=5)
                if stdout.strip():
                    return "background"
            except Exception as e:
                logger.debug(f"Failed to check if {package} is running: {e}", exc_info=True)

            return "unknown"
        except Exception:
            return "unknown"

    def list_installed_apps(self, device_id=None):
        try:
            output = self._run_adb(["shell", "pm", "list", "packages", "-3"], device_id=device_id)[0]
            packages = [
                line.replace("package:", "").strip()
                for line in output.splitlines() if line.startswith("package:")
            ]
            return sorted(packages)
        except Exception:
            return []
