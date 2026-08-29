"""
LAN device discovery via mDNS/DNS-SD (zeroconf).

Discovers devices on the local network that advertise Bonjour/mDNS services
and classifies them into coarse device types (tv, speaker, computer, printer,
smart-home, ...) based on the advertised service types and TXT metadata.

Raw discovery is delegated to the bottom-layer ``zeroconf`` library; this
module provides the typed ``LanDevice`` outlet for the environment domain.
"""

import asyncio
import ipaddress
import logging
import re
import subprocess

from app.core.environment.schemas.models import LanDevice
from app.infrastructure.drivers.system import get_local_ips

logger = logging.getLogger(__name__)

# Service-type substring → coarse device type.
# Order matters: more specific patterns first.
LAN_SERVICE_TYPE_MAP: list[tuple[str, str]] = [
    ("_googlecast", "tv"),  # Chromecast / Android TV / Nest
    ("_airplay", "tv"),  # Apple TV / AirPlay display
    ("_raop", "speaker"),  # AirPlay audio (speakers/receivers)
    ("_spotify-connect", "speaker"),
    ("_hap", "smart_home"),  # HomeKit accessories (lights, fridge, ...)
    ("_homekit", "smart_home"),
    ("_ipp", "printer"),
    ("_scanner", "printer"),
    ("_smb", "computer"),  # file sharing → PC/NAS
    ("_rfb", "computer"),  # VNC / Screen Sharing
    ("_sleep-proxy", "computer"),  # Apple power nap proxy
    ("_ssh", "computer"),
    ("_sftp-ssh", "computer"),
    ("_companion-link", "computer"),  # Apple Continuity
    ("_net-assistant", "computer"),
]

# Deterministic classification priority for multi-service devices:
# a Mac advertising both _smb and _raop is primarily a computer, not a speaker.
DEVICE_TYPE_PRIORITY: list[str] = ["computer", "tv", "printer", "smart_home", "speaker"]

# Compact MAC OUI (first 6 hex chars, lowercase, no colons) → vendor.
# Covers common consumer vendors; a full IEEE OUI DB is not bundled.
OUI_VENDORS: dict[str, str] = {
    # Apple
    "f01898": "Apple",
    "a82066": "Apple",
    "f0989d": "Apple",
    "3c0754": "Apple",
    "acde48": "Apple",
    "90b0ed": "Apple",
    "f0d1a9": "Apple",
    "c8d9d2": "Apple",
    "18e7f4": "Apple",
    "dca904": "Apple",
    "0017f2": "Apple",
    "b8e856": "Apple",
    "8c7b9d": "Apple",
    "6c3e6d": "Apple",
    "04868f": "Apple",
    "101c0c": "Apple",
    "54e4bd": "Apple",
    "f4f15a": "Apple",
    "5cf938": "Apple",
    "f0f65f": "Apple",
    # Xiaomi
    "64693a": "Xiaomi",
    "042004": "Xiaomi",
    "50c90b": "Xiaomi",
    "9c8fbd": "Xiaomi",
    "d4319d": "Xiaomi",
    "640980": "Xiaomi",
    "346195": "Xiaomi",
    "f8a45f": "Xiaomi",
    # Huawei
    "00e0fc": "Huawei",
    "78f5fd": "Huawei",
    "446d57": "Huawei",
    "b0f2c8": "Huawei",
    "8c3fd7": "Huawei",
    "c0ee40": "Huawei",
    "10b7f6": "Huawei",
    "f4c7d0": "Huawei",
    # Samsung
    "98e8fa": "Samsung",
    "f031c3": "Samsung",
    "0012fb": "Samsung",
    "3c2ce4": "Samsung",
    "f4669a": "Samsung",
    "a05e6b": "Samsung",
    "48bf6b": "Samsung",
    "70ad62": "Samsung",
    # TP-Link
    "50c7bf": "TP-Link",
    "14cf92": "TP-Link",
    "a058cb": "TP-Link",
    "28cfda": "TP-Link",
    # Asus
    "244bfe": "Asus",
    "a8032a": "Asus",
    "10870c": "Asus",
    "bcee7b": "Asus",
    # Intel (common in laptops/NUCs)
    "3c7c3f": "Intel",
    "001b21": "Intel",
    "3cfdfe": "Intel",
    "80ee73": "Intel",
    # Realtek
    "00e04c": "Realtek",
    "80fa5b": "Realtek",
    # Broadcom (WiFi cards)
    "1018db": "Broadcom",
    "b03495": "Broadcom",
    # Espressif (ESP8266/ESP32 IoT)
    "18fe34": "Espressif",
    "246f28": "Espressif",
    "3c71bf": "Espressif",
    # Raspberry Pi
    "b827eb": "Raspberry Pi",
    "dca632": "Raspberry Pi",
    "e45f01": "Raspberry Pi",
    # Google / Nest
    "001a11": "Google",
    "3c5ab4": "Google",
    "c4a81d": "Google",
    # Amazon / Echo
    "a48cdb": "Amazon",
    "488393": "Amazon",
    "5c93a2": "Amazon",
    # NVIDIA Shield
    "e8abe8": "NVIDIA",
    # Sonos
    "c8df84": "Sonos",
}


def classify_device_type(service_type: str) -> str:
    """Map a single mDNS service type to a coarse device type."""
    st = (service_type or "").lower()
    for pattern, device_type in LAN_SERVICE_TYPE_MAP:
        if pattern in st:
            return device_type
    return "unknown"


# TXT property keys that identify the model / manufacturer (HomeKit + generic).
_MODEL_KEYS = ("md", "model", "am", "modelname")
_MANUFACTURER_KEYS = ("manufacturer", "mf")


def classify_device_types(service_types: list[str]) -> str:
    """Classify a device from its full set of advertised service types.

    Uses :data:`DEVICE_TYPE_PRIORITY` so a multi-service device (e.g. a Mac
    advertising both ``_smb`` and ``_raop``) is classified deterministically
    as its most specific role rather than whichever service resolved first.
    """
    present = set()
    for service_type in service_types:
        dtype = classify_device_type(service_type)
        if dtype != "unknown":
            present.add(dtype)
    for dtype in DEVICE_TYPE_PRIORITY:
        if dtype in present:
            return dtype
    return "unknown"


def _oui_vendor(mac: str) -> str:
    """Look up a device vendor from the MAC OUI.

    Prefers the compact brand-name map (Apple / Xiaomi / Huawei / ...), falling
    back to the ``manuf`` IEEE OUI database (~30k entries) for broader coverage.
    """
    norm = (mac or "").replace(":", "").lower()
    if len(norm) < 6:
        return ""
    compact = OUI_VENDORS.get(norm[:6], "")
    if compact:
        return compact
    try:
        vendor = _manuf_parser().get_manuf(mac)
    except ImportError:
        return ""
    # manuf may echo the OUI itself for unassigned prefixes — treat as unknown.
    if vendor and vendor != (mac or "")[:8]:
        return vendor
    return ""


_manuf_parser_instance = None


def _manuf_parser():
    global _manuf_parser_instance
    if _manuf_parser_instance is None:
        from manuf import MacParser

        _manuf_parser_instance = MacParser()
    return _manuf_parser_instance


def _pick_txt(txt: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        val = txt.get(key)
        if val:
            return (
                str(val)
                if not isinstance(val, bytes)
                else val.decode("utf-8", "ignore")
            )
    return ""


def _is_randomized_mac(mac: str) -> bool:
    """Detect a locally-administered / privacy-randomized MAC (phone/tablet hint).

    The second hex nibble of the first octet is 2/6/A/E for locally-administered
    (randomized) MACs — the pattern used by iOS/Android privacy MACs.
    """
    first = (mac or "").split(":")[0].lower()
    return len(first) == 2 and first[1] in "26ae"


def _arp_enumerate() -> list[dict]:
    """Enumerate active LAN peers from the OS ARP table (``arp -an``).

    Non-privileged on macOS; reveals devices that do NOT advertise mDNS
    (e.g. idle phones) but have an active IP/MAC entry.
    """
    try:
        result = subprocess.run(
            ["arp", "-an"], capture_output=True, text=True, timeout=3
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    peers = []
    for line in result.stdout.splitlines():
        m = re.search(r"\(([\d.]+)\)\s+at\s+([0-9a-f:]+)", line)
        if m:
            ip, mac = m.group(1), m.group(2)
            if ip.endswith(".255") or ip in ("255.255.255.255", "224.0.0.251"):
                continue
            peers.append({"ip": ip, "mac": mac})
    return peers


def _clean_device_name(raw_name: str) -> str:
    """Strip mDNS noise from a service instance name.

    ``poon的MacBook Pro._ssh._tcp.local.`` -> ``poon的MacBook Pro``
    ``6E9985381633@Mac mini._raop._tcp.local.`` -> ``Mac mini``
    """
    name = raw_name or ""
    if "._" in name:
        name = name.split("._")[0]
    if "@" in name:
        name = name.split("@", 1)[-1]
    return name.strip()


def _record_device(info, service_type: str, devices: dict[str, LanDevice]) -> None:
    """Merge a resolved ServiceInfo into the device map (dedup by IP).

    Collects services + TXT metadata; device_type is classified afterwards via
    :func:`classify_device_types` over the full service set.
    """
    if not info or not info.addresses:
        return
    try:
        ip = str(ipaddress.ip_address(info.addresses[0]))
    except ValueError:
        return

    txt = getattr(info, "decoded_properties", {}) or {}
    name = _clean_device_name(info.name)
    dev = devices.get(ip)
    if dev is None:
        dev = LanDevice(ip=ip, name=name)
        devices[ip] = dev

    if not dev.name:
        dev.name = name
    if not dev.manufacturer:
        dev.manufacturer = _pick_txt(txt, _MANUFACTURER_KEYS)
    if not dev.model:
        dev.model = _pick_txt(txt, _MODEL_KEYS)
    if service_type not in dev.services:
        dev.services.append(service_type)
    if info.port and dev.port is None:
        dev.port = info.port


async def probe_lan_devices(timeout: float = 3.0) -> list[LanDevice]:
    """Probe the local network for devices advertising mDNS services.

    Phase 1 browses ``_services._dns-sd._udp`` to enumerate advertised service
    types; Phase 2 browses each type to resolve device instances (IP / port /
    TXT metadata). Returns typed :class:`LanDevice` entries deduped by IP.
    """
    try:
        from zeroconf import ServiceStateChange
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf
    except ImportError:
        logger.debug("zeroconf not installed; LAN device discovery disabled")
        return []

    azc = AsyncZeroconf()
    devices: dict[str, LanDevice] = {}
    discovered: set[tuple[str, str]] = set()

    async def _resolve(service_type: str, name: str) -> None:
        info = await azc.async_get_service_info(service_type, name)
        if info and info.addresses:
            _record_device(info, service_type, devices)

    def on_change(
        zeroconf,  # noqa: ARG001 (param name required by zeroconf keyword call)
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
            discovered.add((service_type, name))
            # Resolve immediately during the browse window so we capture as many
            # services as possible within the timeout (prevents weak/incomplete
            # classification).
            asyncio.create_task(_resolve(service_type, name))

    # Phase 1 + 2 share a SINGLE timeout window: browse the meta type
    # "_services._dns-sd._udp" and, as each advertised service type is
    # discovered, immediately open a browser for it. This halves the probe
    # latency versus ZeroconfServiceTypes.find (full window) + a second
    # browse window.
    browsers: list[AsyncServiceBrowser] = []
    service_types: set[str] = set()

    def on_type_change(
        zeroconf,  # noqa: ARG001 (param name required by zeroconf keyword call)
        service_type: str,  # noqa: ARG001 (meta-type browse announces types via `name`)
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change == ServiceStateChange.Added and name not in service_types:
            service_types.add(name)
            browsers.append(
                AsyncServiceBrowser(azc.zeroconf, name, handlers=[on_change])
            )

    try:
        type_browser = AsyncServiceBrowser(
            azc.zeroconf,
            "_services._dns-sd._udp.local.",
            handlers=[on_type_change],
        )
        await asyncio.sleep(timeout)
        await type_browser.async_cancel()
        for browser in browsers:
            await browser.async_cancel()

        # Final pass for stragglers discovered late in the window.
        for service_type, name in discovered:
            if not any(d.ip and service_type in d.services for d in devices.values()):
                info = await azc.async_get_service_info(service_type, name)
                if info and info.addresses:
                    _record_device(info, service_type, devices)

        # Deterministic classification over the FULL service set (not first-wins).
        for dev in devices.values():
            if dev.services:
                dev.device_type = classify_device_types(dev.services)
    finally:
        await azc.async_close()

    # Complement with ARP table: reveals devices (e.g. idle phones) that do not
    # advertise mDNS. Randomized MACs are a strong "likely mobile" hint; OUI
    # lookup fills the vendor for otherwise-metadata-less devices.
    for peer in await asyncio.to_thread(_arp_enumerate):
        dev = devices.get(peer["ip"])
        if dev is None:
            dev = LanDevice(ip=peer["ip"], mac=peer["mac"])
            devices[peer["ip"]] = dev
        elif not dev.mac:
            dev.mac = peer["mac"]
        if not dev.manufacturer:
            dev.manufacturer = _oui_vendor(dev.mac)
        if _is_randomized_mac(dev.mac) and dev.device_type == "unknown":
            dev.device_type = "mobile"

    # Exclude the local machine (loopback / own interface IPs) from the LAN view.
    local_ips = get_local_ips()
    devices = {ip: dev for ip, dev in devices.items() if ip not in local_ips}

    return list(devices.values())
