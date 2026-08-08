"""
Bluetooth device discovery on macOS.

Parses ``system_profiler SPBluetoothDataType`` (non-privileged) to enumerate
paired/connected Bluetooth devices. Provides name, address, vendor (from the
Bluetooth SIG company ID) and device type (from the device Minor Type) — the
dimensions that passive LAN discovery (mDNS/ARP) cannot supply for privacy-
randomized phones.

Note: this lists *paired/known* devices only; active inquiry would require
``IOBluetoothDeviceInquiry``.
"""

import logging
import re
import subprocess

from app.core.environment.schemas.models import BluetoothDevice

logger = logging.getLogger(__name__)

# Bluetooth SIG company ID → brand (common consumer vendors).
BT_VENDOR_IDS: dict[str, str] = {
    "0x004c": "Apple",
    "0x010f": "Huawei",
    "0x2717": "Xiaomi",
    "0x0075": "Samsung",
    "0x00e0": "Google",
    "0x0055": "Microsoft",
    "0x05f0": "OnePlus",
    "0x01f4": "OPPO",
    "0x0aee": "Vivo",
    "0x0116": "Realtek",
    "0x013b": "Qualcomm",
    "0x0061": "Sony",
    "0x000a": "Logitech",
}

# Bluetooth Minor Type → coarse device type.
BT_MINOR_TYPE_MAP: dict[str, str] = {
    "mobile phone": "mobile",
    "smartphone": "mobile",
    "tablet": "mobile",
    "headset": "audio",
    "headphones": "audio",
    "earphone": "audio",
    "speaker": "speaker",
    "keyboard": "peripheral",
    "mouse": "peripheral",
    "gamepad": "peripheral",
    "computer": "computer",
    "laptop": "computer",
    "notebook": "computer",
}


def _bt_vendor(vendor_id: str) -> str:
    return BT_VENDOR_IDS.get((vendor_id or "").lower(), "")


def _bt_device_type(minor_type: str) -> str:
    return BT_MINOR_TYPE_MAP.get((minor_type or "").strip().lower(), "unknown")


def probe_bluetooth_devices() -> list[BluetoothDevice]:
    """Enumerate paired/connected Bluetooth devices on macOS.

    Returns an empty list if ``system_profiler`` is unavailable or reports no
    devices. Non-privileged.
    """
    try:
        result = subprocess.run(
            ["system_profiler", "SPBluetoothDataType"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    devices: list[BluetoothDevice] = []
    current: dict[str, str] | None = None

    for line in result.stdout.splitlines():
        # Device names sit at 10 spaces; properties (Address/Vendor/...) at 14.
        name_match = re.match(r"^\s{10}(.+):\s*$", line)
        prop_match = re.match(
            r"^\s{14}(Address|Vendor ID|Product ID|Minor Type):\s*(.+)", line
        )
        if name_match:
            if current:
                devices.append(_build_device(current))
            current = {"name": name_match.group(1).strip()}
        elif prop_match and current is not None:
            current[prop_match.group(1)] = prop_match.group(2).strip()
    if current:
        devices.append(_build_device(current))

    return devices


def _build_device(data: dict[str, str]) -> BluetoothDevice:
    vendor = _bt_vendor(data.get("Vendor ID", ""))
    device_type = _bt_device_type(data.get("Minor Type", ""))
    return BluetoothDevice(
        name=data.get("name", ""),
        address=data.get("Address", ""),
        device_type=device_type,
        vendor=vendor,
        product_id=data.get("Product ID", ""),
    )
