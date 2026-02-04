"""
Environment Discovery - Probes for collecting environment information.
"""

import logging
import os
import re
import socket
import subprocess

from app.core.environment.models import (
    MacOSEnvironment,
    AndroidDevice,
    NetworkStatus,
)

logger = logging.getLogger(__name__)


class EnvironmentProbe:
    """Collects environment information from various sources."""

    @staticmethod
    def probe_macos() -> MacOSEnvironment | None:
        """Probe MacOS host environment."""
        try:
            # OS Version
            os_ver = subprocess.run(
                ["sw_vers", "-productVersion"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()

            # Model
            model = subprocess.run(
                ["sysctl", "-n", "hw.model"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()

            # CPU
            cpu = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()

            # RAM (in GB)
            ram_bytes = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            ram_gb = int(ram_bytes) // (1024**3) if ram_bytes.isdigit() else 0

            # Installed apps
            apps = []
            try:
                app_list = os.listdir("/Applications")
                apps = sorted([a.replace(".app", "") for a in app_list if a.endswith(".app")])
            except Exception:
                pass

            return MacOSEnvironment(
                os_version=os_ver,
                model=model,
                cpu=cpu,
                ram_gb=ram_gb,
                installed_apps=apps,
            )
        except Exception as e:
            logger.warning(f"Failed to probe MacOS environment: {e}")
            return None

    @staticmethod
    def probe_android_devices() -> list[AndroidDevice]:
        """Probe connected Android devices via ADB."""
        devices = []
        try:
            # List devices
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            lines = result.stdout.strip().split("\n")[1:]  # Skip header
            for line in lines:
                if not line.strip() or "offline" in line:
                    continue
                    
                parts = line.split()
                if len(parts) < 2:
                    continue
                    
                device_id = parts[0]
                
                # Get device info
                try:
                    model = subprocess.run(
                        ["adb", "-s", device_id, "shell", "getprop", "ro.product.model"],
                        capture_output=True, text=True, timeout=5
                    ).stdout.strip()
                    
                    version = subprocess.run(
                        ["adb", "-s", device_id, "shell", "getprop", "ro.build.version.release"],
                        capture_output=True, text=True, timeout=5
                    ).stdout.strip()
                    
                    sdk = subprocess.run(
                        ["adb", "-s", device_id, "shell", "getprop", "ro.build.version.sdk"],
                        capture_output=True, text=True, timeout=5
                    ).stdout.strip()
                    
                    # Battery
                    battery_output = subprocess.run(
                        ["adb", "-s", device_id, "shell", "dumpsys", "battery"],
                        capture_output=True, text=True, timeout=5
                    ).stdout
                    battery_match = re.search(r"level:\s*(\d+)", battery_output)
                    battery = int(battery_match.group(1)) if battery_match else 0
                    
                    # Installed packages (3rd party only)
                    packages_output = subprocess.run(
                        ["adb", "-s", device_id, "shell", "pm", "list", "packages", "-3"],
                        capture_output=True, text=True, timeout=10
                    ).stdout
                    packages = [
                        line.replace("package:", "").strip()
                        for line in packages_output.splitlines()
                        if line.startswith("package:")
                    ]
                    
                    devices.append(AndroidDevice(
                        device_id=device_id,
                        model=model,
                        os_version=version,
                        sdk_version=int(sdk) if sdk.isdigit() else 0,
                        battery_percent=battery,
                        installed_packages=sorted(packages),
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
                    
        except FileNotFoundError:
            logger.info("ADB not found, skipping Android device probe")
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
