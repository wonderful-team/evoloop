"""
App Environment Prompt

Centralizes the logic for generating the "Awakening" section of the system prompt.
This ensures both the Supervisor and Skills share the same understanding of the environment.
"""

import asyncio
import logging
import re
from datetime import datetime

from app.core.context.manager import ContextManager
from app.core.context.plugins import plugin_registry
from app.core.environment.utils import collect_cpu_mem
from app.core.tools.manager import tool_manager
from app.infrastructure.drivers.browser import browser_manager
from app.infrastructure.drivers.system import get_disk_usage, get_listening_ports
from app.utils.template import render_template

logger = logging.getLogger(__name__)


def _get_user_lang() -> str:
    """Preferred UI language from the config table (lazy import to avoid an
    infra circular import: this module is reached via the macro engine chain)."""
    from app.infrastructure.config.service import SystemConfigService

    return SystemConfigService.get_language_preference()


class AppEnvironmentPrompt:
    """
    Generates the environment context string based on the current AwakenedState.
    """

    @staticmethod
    def render_environment_block(tips: bool = True, skip_hydrate: bool = False) -> str:
        """
        Render the full 'Awakening' block using localized sensing templates.
        This is the primary interface for autonomous sensing output.
        """
        try:
            ctx = ContextManager.current()
            # Hydrate only when called from a synchronous context. Async callers
            # should already have awaited plugin_registry.ahydrate_context(ctx).
            if not skip_hydrate and not ctx.environment_summaries:
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    plugin_registry.hydrate_context(ctx)

            template_vars = {
                "environment": ctx.environment_summaries, # Now contains raw data
                "current_datetime": __import__("datetime").datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
                "memory_replay": ctx.memory_replay,
                "spatial_awareness": ctx.spatial_awareness,
                "boundaries": ctx.active_boundaries,
                "user_preferences": ctx.metadata.get("user_preferences", {}),
                "user_lang": _get_user_lang(),
                "mcp_inventory": tool_manager.get_mcp_inventory(),
                "browser_status": _get_browser_status(),
                "has_android": ctx.metadata.get("has_android", False),
                "has_macos": ctx.metadata.get("has_macos", False),
                "tips": tips,
                "ctx": ctx,  # Pass full context for working_directory access
            }

            return render_template("core/environment/awakening.prompt.j2", **template_vars)

        except Exception as e:
            logger.exception("Failed to render environment block: %s", e)
            return ""


# Environment Prompt Utilities - Shared logic for building environment awareness sections.


def _get_active_background_tasks() -> list[dict]:
    try:
        from app.core.context import ContextManager
        from app.core.execution.terminal.background import task_manager

        ctx = ContextManager.current()
        thread_id = ctx.thread_id
        if not thread_id:
            return []

        active_tasks = task_manager.get_active_tasks(thread_id)
        return [
            {
                "task_id": t.task_id,
                "title": t.title,
                "status": t.status.value,
                "elapsed_seconds": t.elapsed_seconds,
            }
            for t in active_tasks
        ]
    except Exception:
        logger.exception("Failed to load active background tasks")
        return []


def _get_listening_local_ports() -> list[dict]:
    try:
        ports = get_listening_ports()
        # Deduplicate by port (prefer entries with a pid)
        seen_ports = {}
        for p in ports:
            port = p["port"]
            if port not in seen_ports or (p["pid"] and not seen_ports[port]["pid"]):
                seen_ports[port] = p
        return sorted(seen_ports.values(), key=lambda x: x["port"])
    except Exception:
        logger.exception("Failed to enumerate listening local ports")
        return []


def _parse_docker_host_ports(docker_containers: list[dict]) -> set[int]:
    """Extract host-side ports from Docker container port mappings."""
    host_ports = set()
    for c in docker_containers:
        ports_str = c.get("ports", "")
        if not ports_str:
            continue
        for mapping in ports_str.split(","):
            m = re.search(r":(\d+)->", mapping.strip())
            if m:
                host_ports.add(int(m.group(1)))
    return host_ports


def _docker_host_endpoints(ports_str: str) -> list[str]:
    """Extract host-side endpoints from a Docker ports mapping.

    ``0.0.0.0:18080->80/tcp, [::]:18080->80/tcp`` -> ``['0.0.0.0:18080']``.
    Deduplicates the IPv4/IPv6 bindings of the same port.
    """
    endpoints: dict[int, str] = {}
    for mapping in ports_str.split(","):
        arrow = mapping.find("->")
        if arrow < 0:
            continue
        host_side = mapping[:arrow].strip()
        m = re.search(r":(\d+)$", host_side)
        if not m:
            continue
        endpoints.setdefault(int(m.group(1)), host_side)
    return [endpoints[p] for p in sorted(endpoints)]


def _docker_label(c: dict) -> str:
    """Compact per-container label: bridge IP + container ports, falling back
    to the host-published binding when the bridge IP is unavailable."""
    name = c["name"]
    ports_str = c.get("ports", "")
    ip = c.get("ip")
    if ip:
        container_ports = sorted(
            {int(m) for m in re.findall(r"->(\d+)/", ports_str)}
        )
        if container_ports:
            return f"{name}: {ip}:{','.join(map(str, container_ports))}"
        return f"{name}: {ip}"
    host_endpoints = _docker_host_endpoints(ports_str)
    if host_endpoints:
        return f"{name}: {', '.join(host_endpoints)}"
    return f"{name}: (无外部端口)"


def _normalize_app_name(name: str) -> str:
    """Normalize a process/app name for cross-source matching."""
    return re.sub(r"[\s\-_]+", "", name).lower()


def _get_active_window() -> str | None:
    """Best-effort fetch of the current foreground window/app name."""
    try:
        from app.core.environment import get_current_app_context

        ctx = get_current_app_context()
        return ctx.name or ctx.title or None
    except Exception:
        logger.debug("Could not fetch active window", exc_info=True)
        return None


def build_environment_summaries(relevance: str = "auto", include_full_apps: bool = False) -> dict:
    """
    Build environment awareness data from awakened state.
    Returns a dictionary suitable for templates.

    Args:
        relevance: "android", "macos", "both", or "auto"
        include_full_apps: include the full installed-app list and detailed
            app usage stats (with priority scores). Default False keeps the
            context compact (count + top apps only).
    """
    try:
        from app.core.environment import get_awakened_state

        state = get_awakened_state()
        if not state:
            return {}

        data = {"android_devices": [], "network": None}

        # 1. Host (macOS) Info
        if state.host:
            host_info = {
                "os_name": state.host.os_name,
                "model": state.host.model,
                "cpu": state.host.cpu,
                "os_version": state.host.os_version,
                "running_apps": [],
                "top_apps": [],
                "recently_used_closed": [],
                "app_count": 0,
            }
            if relevance in ["macos", "both", "auto"]:
                if state.host.app_usage_stats:
                    ranked = sorted(
                        state.host.app_usage_stats,
                        key=lambda s: s.priority_score,
                        reverse=True,
                    )
                    host_info["running_apps"] = [s.app_name for s in ranked if s.is_running][:20]
                    host_info["top_apps"] = [s.app_name for s in ranked][:10]
                    host_info["recently_used_closed"] = [
                        a for a in host_info["top_apps"]
                        if a not in host_info["running_apps"]
                    ]
                    if include_full_apps:
                        host_info["app_usage_stats"] = [
                            {
                                "app_name": s.app_name,
                                "priority_score": s.priority_score,
                                "is_running": s.is_running,
                                "total_foreground_ms": s.total_foreground_ms,
                            }
                            for s in ranked
                        ]
                if include_full_apps:
                    running_norm = {
                        _normalize_app_name(a) for a in host_info["running_apps"]
                    }
                    host_info["installed_apps"] = [
                        a for a in (state.host.installed_apps or [])
                        if _normalize_app_name(a) not in running_norm
                    ]
                if state.host.os_name == "macOS":
                    host_info["active_window"] = _get_active_window()
            # Linux specific details
            if state.host.os_name == "Linux":
                host_info["distro"] = state.host.distro
                host_info["sudo_available"] = state.host.sudo_available
                host_info["systemd_services"] = state.host.systemd_services
                host_info["gpus"] = state.host.gpus

            # Real-time telemetry for all platforms (lightweight only)
            try:
                metrics = collect_cpu_mem()
                if metrics:
                    host_info["cpu_percent"] = metrics["cpu_percent"]
                    host_info["memory_percent"] = metrics["mem_percent"]
                    host_info["memory_available_gb"] = round(metrics["mem_available"] / (1024**3), 1)
                disk = get_disk_usage("/")
                if disk:
                    host_info["disk_space"] = disk
            except Exception:
                logger.debug("Failed to collect real-time host telemetry", exc_info=True)

            host_info["current_time"] = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

            data["host"] = host_info

        # 2. Android Info
        if state.android_devices:
            if relevance in ["android", "both", "auto"]:
                for dev in state.android_devices:
                    dev_data = {
                        "is_reachable": dev.is_reachable,
                        "device_id": dev.device_id,
                        "model": dev.model,
                        "os_version": dev.os_version,
                        "battery_percent": dev.battery_percent,
                        "top_pkgs": [],
                        "more_count": 0,
                    }
                    if dev.installed_packages:
                        dev_data["top_pkgs"] = dev.installed_packages
                        dev_data["more_count"] = len(dev.installed_packages)
                    data["android_devices"].append(dev_data)

        # 3. Network
        if state.network:
            data["network"] = {"internet_connected": state.network.internet_connected}

        # 3b. LAN devices discovered via mDNS + ARP, enriched by Bluetooth
        bt_mobiles = [
            b for b in (state.bluetooth_devices or []) if b.device_type == "mobile"
        ]
        _bt_idx = 0
        lan_list = []
        for d in (state.lan_devices or []):
            item = {
                "ip": d.ip,
                "name": d.name,
                "device_type": d.device_type,
                "manufacturer": d.manufacturer,
                "model": d.model,
                "services": d.services,
            }
            # A LAN "mobile" without a name can be cross-referenced with a
            # paired Bluetooth phone to attach its name/vendor.
            if item["device_type"] == "mobile" and not item["name"] and _bt_idx < len(bt_mobiles):
                btd = bt_mobiles[_bt_idx]
                item["name"] = btd.name
                if not item["manufacturer"]:
                    item["manufacturer"] = btd.vendor
                _bt_idx += 1
            lan_list.append(item)
        data["lan_devices"] = lan_list

        # 4. Background Services, Listening Ports, and Docker
        data["running_services"] = _get_active_background_tasks()
        data["docker_containers"] = state.docker_containers
        data["docker_labels"] = []
        for c in state.docker_containers:
            data["docker_labels"].append(_docker_label(c))
        data["active_ports"] = _get_listening_local_ports()
        # Filter Docker container host ports from local service list
        docker_host_ports = _parse_docker_host_ports(state.docker_containers)
        if docker_host_ports:
            data["active_ports"] = [
                svc for svc in data["active_ports"]
                if svc["port"] not in docker_host_ports
            ]
        # Exclude foreground applications (already surfaced via Running Applications)
        running_apps = {
            s.app_name for s in (state.host.app_usage_stats or []) if s.is_running
        }
        if running_apps:
            running_normalized = {_normalize_app_name(n) for n in running_apps}
            data["active_ports"] = [
                svc for svc in data["active_ports"]
                if _normalize_app_name(svc["process"]) not in running_normalized
            ]
        # Group ports per process instance for compact rendering (one line per service)
        by_process: dict[tuple[str, int | None], list[int]] = {}
        for svc in data["active_ports"]:
            key = (svc["process"], svc.get("pid"))
            by_process.setdefault(key, []).append(svc["port"])
        data["service_labels"] = [
            f"{process} (PID {pid}): {', '.join(map(str, sorted(ports)))}"
            if pid else f"{process}: {', '.join(map(str, sorted(ports)))}"
            for (process, pid), ports in sorted(by_process.items(), key=lambda x: (x[0][0], x[0][1] or 0))
        ]

        return data

    except Exception:
        logger.exception("Failed to build environment summaries")
        return {}


def _get_browser_status() -> dict | None:
    """Helper to safely retrieve browser status for prompt injection."""
    try:
        return browser_manager.get_status()
    except ImportError:
        return None
    except Exception:
        logger.debug("Failed to get browser status", exc_info=True)
        return None
