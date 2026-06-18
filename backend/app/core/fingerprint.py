"""
Cross-platform hardware fingerprint for device identification.

Provides a stable machine-level identifier that survives:
- Application reinstalls (if user data is preserved)
- Token/logout cycles
- Minor hardware changes

Does NOT survive:
- OS reinstall (machine-id changes)
- Deliberate fingerprint spoofing (this is not a DRM solution)

The fingerprint is a SHA256 hash of platform-specific identifiers,
truncated to 32 hex characters for compactness.
"""

import hashlib
import logging
import os
import platform
import subprocess

logger = logging.getLogger(__name__)


def get_hardware_fingerprint() -> str:
    """
    Get a stable hardware fingerprint for the current machine.

    Falls back gracefully if platform-specific APIs are unavailable.
    """
    system = platform.system()
    raw = ""

    try:
        if system == "Darwin":
            raw = _get_macos_uuid()
        elif system == "Windows":
            raw = _get_windows_machine_guid()
        elif system == "Linux":
            raw = _get_linux_machine_id()
        else:
            raw = _fallback()
    except Exception as e:
        logger.warning(f"Failed to get hardware fingerprint: {e}")
        raw = _fallback()

    # Normalize and hash
    normalized = raw.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


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
                # Line looks like: "IOPlatformUUID" = "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
                parts = line.split('"')
                if len(parts) >= 4:
                    return parts[-2]
    except Exception as e:
        logger.debug(f"ioreg failed: {e}")

    # Fallback: try system_profiler
    try:
        result = subprocess.run(
            ["system_profiler", "SPHardwareDataType", "-xml"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Simple text extraction from XML
        import re
        match = re.search(r"<key>platform_UUID</key>\s*<string>([^<]+)</string>", result.stdout)
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f"system_profiler failed: {e}")

    return _fallback()


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
        logger.debug(f"Windows registry read failed: {e}")

    # Fallback: wmic
    try:
        result = subprocess.run(
            ["wmic", "csproduct", "get", "UUID"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
        if len(lines) >= 2 and lines[1].lower() != "ffffffff-ffff-ffff-ffff-ffffffffffff":
            return lines[1]
    except Exception as e:
        logger.debug(f"wmic failed: {e}")

    return _fallback()


def _get_linux_machine_id() -> str:
    """Read /etc/machine-id or /var/lib/dbus/machine-id."""
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        try:
            with open(path, "r") as f:
                content = f.read().strip()
                if content and content != "uninitialized":
                    return content
        except (FileNotFoundError, PermissionError):
            continue

    # Fallback: try dmidecode
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
        logger.debug(f"dmidecode failed: {e}")

    return _fallback()


def _fallback() -> str:
    """Last resort: hostname + username composite."""
    import getpass

    hostname = platform.node() or "unknown"
    username = getpass.getuser() or "unknown"
    return f"{hostname}:{username}"
