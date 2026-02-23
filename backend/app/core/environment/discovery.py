"""
Environment Discovery - Probes for collecting environment information.
"""
import asyncio
import logging
import socket

from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
from app.core.environment.models import (
    AndroidDevice,
    MacOSEnvironment,
    NetworkStatus,
)

logger = logging.getLogger(__name__)


class EnvironmentProbe:
    """Collects environment information from various sources."""

    @staticmethod
    async def probe_macos() -> MacOSEnvironment | None:
        """Probe MacOS host environment using macos_driver."""
        from app.infrastructure.drivers.macos import macos_driver
        from app.core.environment.explorers.dynamic_apps import DynamicAppTriage

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

            # Autonomous triage for discovered apps
            try:
                triage = DynamicAppTriage()
                await triage.sync_dynamic_apps(macos_apps=apps)
            except Exception as triage_e:
                logger.warning(f"[EnvironmentProbe] macOS dynamic app triage failed: {triage_e}")

            return MacOSEnvironment(
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
                        except:
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

                    # Autonomous triage for discovered packages
                    try:
                        triage = DynamicAppTriage()
                        await triage.sync_dynamic_apps(android_packages=packages)
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
                except:
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
                except:
                    return []

            local_ips = await asyncio.to_thread(_get_ips)
        except Exception:
            pass

        return NetworkStatus(
            internet_connected=internet_connected,
            local_ips=local_ips,
        )
