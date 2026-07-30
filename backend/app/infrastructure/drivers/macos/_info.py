import logging
import subprocess
from typing import Any, cast

logger = logging.getLogger(__name__)


class InfoMixin:
    _cached_scale_factor = None

    @classmethod
    def get_screen_size(cls):
        script = 'tell application "Finder" to get bounds of window of desktop'
        try:
            output = cls.run_applescript(script)
            parts = [int(p.strip()) for p in output.split(",")]
            return parts[2], parts[3]
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
            return 1920, 1080

    @classmethod
    def get_ui_scale_factor(cls):
        if cls._cached_scale_factor is not None:
            return cls._cached_scale_factor

        try:
            import Quartz
            display_id = Quartz.CGMainDisplayID()
            # backingScaleFactor: 2.0 on Retina, 1.0 on non-Retina
            scale = Quartz.CGDisplayBackingScaleFactor(display_id)
            scale = round(scale, 1) if scale > 0 else 1.0
            cls._cached_scale_factor = scale
            logger.info(f"[MacOSDriver] UI scale factor detected and cached: {scale}x")
            return scale
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"[MacOSDriver] Failed to calculate scale factor: {e}")
            return 1.0

    @staticmethod
    def get_system_info():
        import platform
        import plistlib

        try:
            result = subprocess.run(
                ["sw_vers", "--productName"], capture_output=True, text=True, timeout=5
            )
            product_name = result.stdout.strip()

            result = subprocess.run(
                ["sw_vers", "--productVersion"], capture_output=True, text=True, timeout=5
            )
            version = result.stdout.strip()

            result = subprocess.run(
                ["sw_vers", "--buildVersion"], capture_output=True, text=True, timeout=5
            )
            build = result.stdout.strip()

            model = platform.processor() or "Unknown"

            ram = "Unknown"
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
                )
                ram_bytes = int(result.stdout.strip())
                ram = f"{ram_bytes // (1024**3)} GB"
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
                pass

            return {
                "model": model,
                "os_version": f"{product_name} {version} ({build})",
                "memory": ram,
                "platform": "macos",
            }
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            return {"error": str(e)}
