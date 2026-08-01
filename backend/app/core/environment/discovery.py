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

# Background dynamic-app triage tasks created by EnvironmentProbe.
# Stored so they can be cancelled cleanly during shutdown.
_dynamic_triage_tasks: set[asyncio.Task] = set()


def _register_triage_task(task: asyncio.Task) -> None:
    """Track a background triage task and remove it when it finishes."""
    _dynamic_triage_tasks.add(task)
    task.add_done_callback(_dynamic_triage_tasks.discard)


async def cancel_dynamic_triage_tasks() -> None:
    """Cancel all pending dynamic-app triage tasks and wait for them."""
    tasks = list(_dynamic_triage_tasks)
    _dynamic_triage_tasks.clear()
    for task in tasks:
        if task.done():
            continue
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.debug("[EnvironmentProbe] Dynamic triage tasks cancelled")


class EnvironmentProbe:
    """Collects environment information from various sources."""

    @staticmethod
    def get_inferred_device_type() -> str:
        """
        根据唤醒状态和系统/硬件特征动态推导设备类型（限制在 20 字符以内）。
        优先读取用户显式配置覆盖，其次根据操作系统与硬件特征动态判定。
        """
        # 1. 允许通过显式配置手动覆盖（支持任意自定义类型如 "embedded", "raspberry_pi"）
        if settings.EVOCLOUD_DEVICE_TYPE:
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
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)
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
        os_name = platform.system()

        if not settings.ENABLE_ENVIRONMENT_CONTROLS:
            # If environment controls are disabled, return a basic host profile (safe and read-only)
            # This ensures the Agent knows the target OS even on headless servers/sandboxes.
            try:
                ram_gb = int(psutil.virtual_memory().total / (1024 ** 3))
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug(f"Failed to get RAM info: {e}")
                ram_gb = 0

            return HostEnvironment(
                os_name="macOS" if os_name == "Darwin" else os_name,
                os_version=platform.release() if os_name != "Darwin" else (platform.mac_ver()[0] or "Unknown"),
                model="Mac" if os_name == "Darwin" else f"{os_name} Host",
                cpu=platform.processor() or "Unknown",
                ram_gb=ram_gb,
                installed_apps=[],
                app_usage_stats=[]
            )

        if os_name == "Darwin":
            return await EnvironmentProbe._probe_macos_impl()
        else:
            return await EnvironmentProbe._probe_standard_os_impl(os_name)

    @staticmethod
    async def _probe_standard_os_impl(os_name: str) -> HostEnvironment | None:
        """Standard host probe for Linux and Windows."""
        try:
            ram_gb = int(psutil.virtual_memory().total / (1024 ** 3))
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"Failed to get RAM info: {e}")
            ram_gb = 0
            
        host_env = HostEnvironment(
            os_name=os_name,
            os_version=platform.release(),
            model=f"{os_name} Host",
            cpu=platform.processor() or "Unknown",
            ram_gb=ram_gb,
            installed_apps=[],
            app_usage_stats=[]
        )

        if os_name == "Linux":
            import shutil
            import subprocess

            # 1. Distro Details
            distro = "Linux"
            try:
                info = platform.freedesktop_os_release()
                distro = f"{info.get('NAME', 'Linux')} {info.get('VERSION_ID', '')}"
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
                try:
                    if os.path.exists("/etc/os-release"):
                        with open("/etc/os-release", "r") as f:
                            for line in f:
                                if line.startswith("PRETTY_NAME="):
                                    distro = line.split("=", 1)[1].strip().strip('"')
                                    break
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.debug("Suppressed error: %s", e, exc_info=True)
            host_env.distro = distro

            # 2. Sudo availability (without password)
            def _check_sudo():
                try:
                    res = subprocess.run(['sudo', '-n', 'true'], capture_output=True, timeout=1.0)
                    return res.returncode == 0
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
                    return False
            host_env.sudo_available = await asyncio.to_thread(_check_sudo)

            # 3. Disk Space in current directory
            def _get_disk_space():
                try:
                    total, used, free = shutil.disk_usage(".")
                    return {
                        "total_gb": round(total / (2**30), 1),
                        "free_gb": round(free / (2**30), 1),
                        "percent_used": round((used / total) * 100, 1)
                    }
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.debug("Suppressed error: %s", e, exc_info=True)
                    return None
            host_env.disk_space = await asyncio.to_thread(_get_disk_space)

            # 4. Active Systemd Services
            def _get_systemd_services():
                try:
                    res = subprocess.run(
                        ['systemctl', 'list-units', '--type=service', '--state=running', '--no-legend'],
                        capture_output=True,
                        text=True,
                        timeout=1.5
                    )
                    if res.returncode != 0:
                        return []
                    services = []
                    for line in res.stdout.strip().split('\n'):
                        parts = line.split()
                        if parts:
                            name = parts[0].replace('.service', '')
                            if any(svc in name for svc in ('nginx', 'mysql', 'postgres', 'redis', 'docker', 'apache', 'mongodb', 'memcached')):
                                services.append(name)
                    return services
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
                    return []
            host_env.systemd_services = await asyncio.to_thread(_get_systemd_services)

            # 5. GPU Devices
            def _get_gpus():
                try:
                    res = subprocess.run(
                        ['nvidia-smi', '--query-gpu=gpu_name,memory.total', '--format=csv,noheader,nounits'],
                        capture_output=True,
                        text=True,
                        timeout=1.5
                    )
                    if res.returncode == 0:
                        return [line.strip() for line in res.stdout.strip().split('\n') if line.strip()]
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.debug("Suppressed error: %s", e, exc_info=True)
                return []
            host_env.gpus = await asyncio.to_thread(_get_gpus)

        return host_env

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
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"[EnvironmentProbe] UsageRanker failed (non-fatal): {e}")

            # Autonomous triage for discovered apps (run in background to avoid blocking startup)
            try:
                triage = DynamicAppTriage()
                # Run in background - don't block startup for LLM classification
                task = asyncio.create_task(triage.sync_dynamic_apps(macos_apps=apps))
                _register_triage_task(task)
                global _logged_macos_triage
                if not _logged_macos_triage:
                    logger.info("[EnvironmentProbe] macOS dynamic app triage scheduled (first time)")
                    _logged_macos_triage = True
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as triage_e:
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
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
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
                        task = asyncio.create_task(triage.sync_dynamic_apps(android_packages=packages))
                        _register_triage_task(task)
                        # Only log once per device to avoid repetitive logs
                        if device_id not in _logged_device_ids:
                            logger.info(f"[EnvironmentProbe] Android triage scheduled for {device_id} (first time)")
                            _logged_device_ids.add(device_id)
                    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as triage_e:
                        logger.warning(f"[EnvironmentProbe] Android dynamic app triage failed: {triage_e}")

                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.warning(f"Failed to get info for device {device_id}: {e}")
                    devices.append(AndroidDevice(
                        device_id=device_id,
                        model="Unknown",
                        os_version="Unknown",
                        sdk_version=0,
                        battery_percent=0,
                        is_reachable=False,
                    ))

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
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
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)

        # Get local IPs
        try:
            def _get_ips():
                try:
                    hostname = socket.gethostname()
                    return socket.gethostbyname_ex(hostname)[2]
                except OSError:
                    return []

            local_ips = await asyncio.to_thread(_get_ips)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)

        return NetworkStatus(
            internet_connected=internet_connected,
            local_ips=local_ips,
        )

    @staticmethod
    async def probe_docker_containers() -> list[dict]:
        """Probe running Docker containers."""
        try:
            import subprocess
            def _run_docker_ps():
                try:
                    res = subprocess.run(
                        ['docker', 'ps', '--format', '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'],
                        capture_output=True,
                        text=True,
                        timeout=1.5
                    )
                    if res.returncode != 0:
                        return []
                    containers = []
                    output = res.stdout.strip()
                    if not output:
                        return []
                    for line in output.split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 5:
                            containers.append({
                                "id": parts[0],
                                "name": parts[1],
                                "image": parts[2],
                                "status": parts[3],
                                "ports": parts[4]
                            })
                    return containers
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
                    return []
            return await asyncio.to_thread(_run_docker_ps)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
            return []
