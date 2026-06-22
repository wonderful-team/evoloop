"""
Environment Discovery - Probes for collecting environment information.
"""
import asyncio
import logging
import os
import platform
import socket

import psutil

from app.core.config import settings
from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
from app.core.environment.models import (
    AndroidDevice,
    HostEnvironment,
    NetworkStatus,
)

logger = logging.getLogger(__name__)

# Track logged device IDs to avoid repetitive "scheduled" logs
_logged_device_ids: set[str] = set()
_logged_macos_triage: bool = False


class EnvironmentProbe:
    """Collects environment information from various sources."""

    @staticmethod
    def get_inferred_device_type() -> str:
        """
        根据唤醒状态和系统/硬件特征动态推导设备类型（限制在 20 字符以内）。
        优先读取用户显式配置覆盖，其次根据操作系统与硬件特征动态判定。
        """
        # 1. 允许通过显式配置手动覆盖（支持任意自定义类型如 "embedded", "raspberry_pi"）
        if getattr(settings, "EVOCLOUD_DEVICE_TYPE", None):
            val = settings.EVOCLOUD_DEVICE_TYPE
            return val[:20] if len(val) > 20 else val

        # 2. 动态探测 Android 环境
        if os.environ.get("ANDROID_ROOT") or os.path.exists("/system/bin/app_process"):
            return "android"

        # 3. 动态探测嵌入式 Linux 环境 (如树莓派/香橙派)
        if os.path.exists("/proc/device-tree/model"):
            try:
                with open("/proc/device-tree/model", "r") as f:
                    model_info = f.read().lower()
                    if "raspberry pi" in model_info or "orange pi" in model_info or "embedded" in model_info:
                        return "embedded"
            except Exception:
                pass
        if os.path.exists("/sys/class/gpio"):
            return "embedded"

        # 4. 动态检测图形化显示服务器环境（适用于标准 Linux / Windows）
        has_display = any(os.environ.get(var) for var in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_CURRENT_DESKTOP"))
        if has_display or settings.ENABLE_ENVIRONMENT_CONTROLS:
            return "desktop"

        # 5. 动态检测 macOS (Darwin)
        if platform.system() == "Darwin":
            return "desktop"

        # 6. 使用 AwakenedState 进行进一步检测 (如果有)
        from app.core.environment.state import get_awakened_state
        state = get_awakened_state()
        if state and state.host:
            if state.host.os_name == "macOS":
                return "desktop"

        # 7. 保底回退为 server
        return "server"

    @staticmethod
    async def probe_host() -> HostEnvironment | None:
        """Probe host environment (macOS, Linux, Windows)."""
        if not settings.ENABLE_ENVIRONMENT_CONTROLS:
            return None

        os_name = platform.system()

        if os_name == "Darwin":
            return await EnvironmentProbe._probe_macos_impl()
        else:
            return await EnvironmentProbe._probe_standard_os_impl(os_name)

    @staticmethod
    async def _probe_standard_os_impl(os_name: str) -> HostEnvironment | None:
        """Standard host probe for Linux and Windows."""
        try:
            ram_gb = int(psutil.virtual_memory().total / (1024 ** 3))
        except ImportError:
            ram_gb = 0
            
        return HostEnvironment(
            os_name=os_name,
            os_version=platform.release(),
            model=f"{os_name} Host",
            cpu=platform.processor() or "Unknown",
            ram_gb=ram_gb,
            installed_apps=[],
            app_usage_stats=[]
        )

    @staticmethod
    async def _probe_macos_impl() -> HostEnvironment | None:
        """Probe MacOS host environment using macos_driver."""
        from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
        from app.infrastructure.drivers.macos import macos_driver

        try:
            # Run blocking driver calls in threads
            info = await asyncio.to_thread(macos_driver.get_system_info)
            if "error" in info:
                logger.warning(f"MacOS Driver info failed: {info['error']}")
                return None

            apps = await asyncio.to_thread(macos_driver.list_installed_apps)

            # rank apps by usage priority
            usage_stats = []
            try:
                from app.core.environment.usage.ranker import UsageRanker
                # rank_macos_apps performs shell commands, run in thread
                usage_stats = await asyncio.to_thread(UsageRanker.rank_macos_apps, apps, top_n=10)
                logger.info(f"[EnvironmentProbe] UsageRanker: top app = "
                            f"{usage_stats[0].app_name!r} (score={usage_stats[0].priority_score})"
                            if usage_stats else "[EnvironmentProbe] UsageRanker: no usage data")
            except Exception as e:
                logger.warning(f"[EnvironmentProbe] UsageRanker failed (non-fatal): {e}")

            # Autonomous triage for discovered apps (run in background to avoid blocking startup)
            try:
                triage = DynamicAppTriage()
                # Run in background - don't block startup for LLM classification
                asyncio.create_task(triage.sync_dynamic_apps(macos_apps=apps))
                global _logged_macos_triage
                if not _logged_macos_triage:
                    logger.info("[EnvironmentProbe] macOS dynamic app triage scheduled (first time)")
                    _logged_macos_triage = True
            except Exception as triage_e:
                logger.warning(f"[EnvironmentProbe] macOS dynamic app triage failed: {triage_e}")

            return HostEnvironment(
                os_name="macOS",
                os_version=info.get("os_version", "Unknown"),
                model=info.get("model", "Unknown"),
                cpu=info.get("cpu", "Unknown"),
                ram_gb=info.get("ram_gb", 0),
                installed_apps=apps,
                app_usage_stats=usage_stats,
            )
        except Exception as e:
            logger.warning(f"Failed to probe MacOS environment: {e}", exc_info=True)
            return None

    @staticmethod
    async def probe_android_devices() -> list[AndroidDevice]:
        """Probe connected Android devices via ADB."""
        if not settings.ENABLE_ENVIRONMENT_CONTROLS:
            return []

        from app.infrastructure.drivers.adb import adb_driver

        devices = []
        try:
            # List devices using singleton driver
            raw_devices = await asyncio.to_thread(adb_driver.list_devices)

            for dev in raw_devices:
                device_id = dev["serial"]
                status = dev["status"]

                if status != "device":
                    continue

                # Get device info
                try:
                    info = await asyncio.to_thread(adb_driver.get_system_info, device_id)
                    packages = await asyncio.to_thread(adb_driver.list_installed_apps, device_id)

                    # Fallback for battery since get_system_info handles it as string
                    # But we want int for models
                    battery_percent = 0
                    if "battery" in info and "%" in info["battery"]:
                        try:
                            battery_percent = int(info["battery"].replace("%", ""))
                        except ValueError:
                            pass

                    devices.append(AndroidDevice(
                        device_id=device_id,
                        model=info.get("model", "Unknown"),
                        os_version=info.get("os_version", "Unknown"),
                        sdk_version=0,  # Could be added to adb_driver if needed
                        battery_percent=battery_percent,
                        installed_packages=packages,
                        is_reachable=True,
                    ))

                    # Autonomous triage for discovered packages (run in background)
                    try:
                        triage = DynamicAppTriage()
                        asyncio.create_task(triage.sync_dynamic_apps(android_packages=packages))
                        # Only log once per device to avoid repetitive logs
                        if device_id not in _logged_device_ids:
                            logger.info(f"[EnvironmentProbe] Android triage scheduled for {device_id} (first time)")
                            _logged_device_ids.add(device_id)
                    except Exception as triage_e:
                        logger.warning(f"[EnvironmentProbe] Android dynamic app triage failed: {triage_e}")

                except Exception as e:
                    logger.warning(f"Failed to get info for device {device_id}: {e}")
                    devices.append(AndroidDevice(
                        device_id=device_id,
                        model="Unknown",
                        os_version="Unknown",
                        sdk_version=0,
                        battery_percent=0,
                        is_reachable=False,
                    ))

        except Exception as e:
            logger.warning(f"Failed to probe Android devices: {e}")

        return devices

    @staticmethod
    async def probe_network() -> NetworkStatus:
        """Probe network connectivity."""
        internet_connected = False
        local_ips = []

        # Check internet connectivity
        try:
            # Socket connection is blocking, use to_thread
            def _check_internet():
                try:
                    with socket.create_connection(("8.8.8.8", 53), timeout=3) as _:
                        return True
                except OSError:
                    return False

            internet_connected = await asyncio.to_thread(_check_internet)
        except Exception:
            pass

        # Get local IPs
        try:
            def _get_ips():
                try:
                    hostname = socket.gethostname()
                    return socket.gethostbyname_ex(hostname)[2]
                except OSError:
                    return []

            local_ips = await asyncio.to_thread(_get_ips)
        except Exception:
            pass

        return NetworkStatus(
            internet_connected=internet_connected,
            local_ips=local_ips,
        )
