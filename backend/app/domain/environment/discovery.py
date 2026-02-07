"""
Environment Discovery - Probes for collecting environment information.
"""

import logging
import os
import re
import socket
import subprocess

from app.domain.environment.models import (
    MacOSEnvironment,
    AndroidDevice,
    NetworkStatus,
)

logger = logging.getLogger(__name__)


class EnvironmentProbe:
    """Collects environment information from various sources."""

    @staticmethod
    def probe_macos() -> MacOSEnvironment | None:
        """Probe MacOS host environment using macos_driver."""
        from app.domain.tools.environment.drivers.macos import macos_driver

        try:
            info = macos_driver.get_system_info()
            if "error" in info:
                logger.warning(f"MacOS Driver info failed: {info['error']}")
                return None

            apps = macos_driver.list_installed_apps()

            return MacOSEnvironment(
                os_version=info.get("os_version", "Unknown"),
                model=info.get("model", "Unknown"),
                cpu=info.get("cpu", "Unknown"),
                ram_gb=info.get("ram_gb", 0),
                installed_apps=apps,
            )
        except Exception as e:
            logger.warning(f"Failed to probe MacOS environment: {e}")
            return None

    @staticmethod
    def probe_android_devices() -> list[AndroidDevice]:
        """Probe connected Android devices via ADB."""
        from app.domain.tools.environment.drivers.adb import adb_driver

        devices = []
        try:
            # List devices using singleton driver
            raw_devices = adb_driver.list_devices()

            for dev in raw_devices:
                device_id = dev["serial"]
                status = dev["status"]

                if status != "device":
                    continue

                # Get device info
                try:
                    info = adb_driver.get_system_info(device_id)
                    packages = adb_driver.list_installed_apps(device_id)

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
    def probe_network() -> NetworkStatus:
        """Probe network connectivity."""
        internet_connected = False
        local_ips = []

        # Check internet connectivity
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            internet_connected = True
        except Exception:
            pass

        # Get local IPs
        try:
            hostname = socket.gethostname()
            local_ips = socket.gethostbyname_ex(hostname)[2]
        except Exception:
            pass

        return NetworkStatus(
            internet_connected=internet_connected,
            local_ips=local_ips,
        )
