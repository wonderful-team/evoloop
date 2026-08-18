"""
System probe driver — bottom-layer owner of raw OS probing.

Consolidates ``psutil`` / ``platform`` / ``subprocess`` / ``shutil`` usage so
middle-layer modules (``device.py``, ``telemetry.py``, ``environment``) consume
typed helpers instead of reaching into raw system APIs directly.

Discovery-specific probes (sudo, systemd services, GPUs, docker) stay in
``app.core.environment.discovery`` — this module only owns *generic* system
facts (hostname, OS, CPU, memory, disk, machine id, running processes).
"""

import logging
import platform
import shutil
import socket
import subprocess

import psutil

logger = logging.getLogger(__name__)


def get_hostname() -> str:
    """Return the local machine hostname, or ``""`` if unavailable."""
    return platform.node() or ""


def get_local_ips() -> set[str]:
    """Return all local IPv4 addresses (loopback + every interface)."""
    ips = {"127.0.0.1"}
    try:
        for addrs in psutil.net_if_addrs().values():
            for addr in addrs:
                if addr.family.name == "AF_INET":
                    ips.add(addr.address)
    except Exception:
        logger.debug("get_local_ips: interface enumeration failed", exc_info=True)
        try:
            ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            pass
    return ips


def get_os_name() -> str:
    """Return ``platform.system()`` (e.g. ``Darwin`` / ``Linux`` / ``Windows``)."""
    return platform.system()


def get_os_platform() -> str:
    """Return a ``platform.platform()`` string describing the local OS."""
    return platform.platform()


def get_os_release() -> str:
    """Return the OS release string (``platform.release()``)."""
    return platform.release()


def get_macos_version() -> str:
    """Return the macOS version string, or ``"Unknown"``."""
    return platform.mac_ver()[0] or "Unknown"


def get_freedesktop_release() -> dict:
    """Return ``platform.freedesktop_os_release()`` or ``{}``."""
    try:
        return platform.freedesktop_os_release()
    except Exception:
        return {}


def get_processor() -> str:
    """Return ``platform.processor()`` or ``"Unknown"``."""
    return platform.processor() or "Unknown"


def get_memory_total_gb() -> int:
    """Return total physical memory in GiB (integer)."""
    try:
        return int(psutil.virtual_memory().total / (1024**3))
    except Exception:
        return 0


def get_cpu_mem() -> dict | None:
    """Collect CPU and memory metrics defensively.

    Returns a dict with ``cpu_percent``, ``load_avg``, ``mem_percent``,
    ``mem_available``, ``mem_used`` and ``mem_total``, or ``None`` if the
    snapshot could not be gathered.
    """
    try:
        mem = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "load_avg": (
                psutil.getloadavg() if hasattr(psutil, "getloadavg") else []
            ),
            "mem_percent": mem.percent,
            "mem_available": mem.available,
            "mem_used": mem.used,
            "mem_total": mem.total,
        }
    except Exception:
        logger.debug("Failed to collect host CPU/memory telemetry", exc_info=True)
        return None


def get_disk_usage(path: str = "/") -> dict | None:
    """Return disk usage for ``path`` as ``{total_gb, free_gb, percent_used}``."""
    try:
        disk = shutil.disk_usage(path)
        return {
            "total_gb": round(disk.total / (2**30), 1),
            "free_gb": round(disk.free / (2**30), 1),
            "percent_used": round((disk.used / disk.total) * 100, 1),
        }
    except Exception:
        logger.debug("Failed to read disk usage for %s", path, exc_info=True)
        return None


def get_running_processes(fields: tuple[str, ...] = ("pid", "name")) -> list:
    """Return running processes via ``psutil.process_iter`` (defensive)."""
    procs = []
    try:
        for p in psutil.process_iter(list(fields)):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        logger.debug("Failed to enumerate running processes", exc_info=True)
    return procs


def get_listening_ports() -> list[dict]:
    """Return listening inet ports as ``[{port, pid, process}]`` (defensive)."""
    ports = []
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    for conn in p.connections(kind="inet"):
                        if conn.status == "LISTEN":
                            ports.append(
                                {
                                    "port": conn.laddr.port,
                                    "pid": p.info["pid"],
                                    "process": p.info["name"] or "Unknown",
                                }
                            )
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
    except Exception:
        logger.debug("Failed to enumerate listening ports", exc_info=True)
    return ports


def get_machine_id() -> str:
    """Return a stable machine identifier (OS-specific UUID / machine-id)."""
    system = get_os_name()
    if system == "Darwin":
        return _get_macos_uuid()
    if system == "Windows":
        return _get_windows_machine_guid()
    if system == "Linux":
        return _get_linux_machine_id()
    return _fallback_identity()


def _get_macos_uuid() -> str:
    """Read IOPlatformUUID from ioreg (survives OS reinstall)."""
    try:
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.split("\n"):
            if "IOPlatformUUID" in line:
                parts = line.split('"')
                if len(parts) >= 4:
                    return parts[-2]
    except Exception as e:
        logger.debug(f"ioreg failed: {e}", exc_info=True)

    try:
        result = subprocess.run(
            ["system_profiler", "SPHardwareDataType", "-xml"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        import re

        match = re.search(
            r"<key>platform_UUID</key>\s*<string>([^<]+)</string>", result.stdout
        )
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f"system_profiler failed: {e}", exc_info=True)

    return _fallback_identity()


def _get_windows_machine_guid() -> str:
    """Read MachineGuid from Windows Registry."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception as e:
        logger.debug(f"Windows registry read failed: {e}", exc_info=True)

    try:
        result = subprocess.run(
            ["wmic", "csproduct", "get", "UUID"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [line.strip() for line in result.stdout.split("\n") if line.strip()]
        if len(lines) >= 2 and lines[1].lower() != "ffffffff-ffff-ffff-ffff-ffffffffffff":
            return lines[1]
    except Exception as e:
        logger.debug(f"wmic failed: {e}", exc_info=True)

    return _fallback_identity()


def _get_linux_machine_id() -> str:
    """Read /etc/machine-id or /var/lib/dbus/machine-id."""
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        try:
            with open(path) as f:
                content = f.read().strip()
                if content and content != "uninitialized":
                    return content
        except (FileNotFoundError, PermissionError):
            continue

    try:
        result = subprocess.run(
            ["dmidecode", "-s", "system-uuid"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        uuid = result.stdout.strip()
        if uuid and uuid.lower() != "not settable":
            return uuid
    except Exception as e:
        logger.debug(f"dmidecode failed: {e}", exc_info=True)

    return _fallback_identity()


def _fallback_identity() -> str:
    """Last resort: hostname + username composite."""
    import getpass

    hostname = get_hostname() or "unknown"
    username = getpass.getuser() or "unknown"
    return f"{hostname}:{username}"
