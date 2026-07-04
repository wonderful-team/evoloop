"""
App Environment Prompt

Centralizes the logic for generating the "Awakening" section of the system prompt.
This ensures both the Supervisor and Skills share the same understanding of the environment.
"""
import logging

from app.core.context.manager import ContextManager
from app.core.context.plugins import plugin_registry
from app.core.tools.manager import tool_manager
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.drivers.browser import browser_manager
from app.utils import render_template

logger = logging.getLogger(__name__)


class AppEnvironmentPrompt:
    """
    Generates the environment context string based on the current AwakenedState.
    """

    @staticmethod
    def build(messages: list[dict] = None) -> str:
        """Legacy alias for render_environment_block."""
        return AppEnvironmentPrompt.render_environment_block()

    @staticmethod
    def render_environment_block(tips: bool = True, skip_hydrate: bool = False) -> str:
        """
        Render the full 'Awakening' block using localized sensing templates.
        This is the primary interface for autonomous sensing output.
        """
        try:
            ctx = ContextManager.current()
            # Hydrate if not already done (usually done by middleware/registry)
            if not skip_hydrate and not ctx.environment_summaries:
                plugin_registry.hydrate_context(ctx)

            template_vars = {
                "environment": ctx.environment_summaries, # Now contains raw data
                "current_datetime": __import__("datetime").datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
                "memory_replay": ctx.memory_replay,
                "spatial_awareness": ctx.spatial_awareness,
                "boundaries": ctx.active_boundaries,
                "user_preferences": ctx.metadata.get("user_preferences", {}),
                "user_lang": SystemConfigService.get_language_preference(),
                "mcp_inventory": tool_manager.get_mcp_inventory(),
                "browser_status": _get_browser_status(),
                "has_android": ctx.metadata.get("has_android", False),
                "has_macos": ctx.metadata.get("has_macos", False),
                "is_subtask": ctx.metadata.get("is_subtask", False),
                "tips": tips,
                "ctx": ctx,  # Pass full context for working_directory access
            }

            return render_template("core/environment/awakening.prompt.j2", **template_vars)

        except Exception as e:
            logger.error(f"Failed to render environment block: {e}")
            return ""


# Environment Prompt Utilities - Shared logic for building environment awareness sections.

def _get_active_background_tasks() -> list[dict]:
    try:
        from app.core.context import ContextManager
        from app.core.tools.background import task_manager

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
        return []


def _get_listening_local_ports() -> list[dict]:
    try:
        import psutil
        import warnings
        ports = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    for conn in p.connections(kind='inet'):
                        if conn.status == 'LISTEN':
                            ports.append({
                                "port": conn.laddr.port,
                                "pid": p.info['pid'],
                                "process": p.info['name'] or "Unknown"
                            })
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
        # Deduplicate by port
        seen_ports = {}
        for p in ports:
            port = p["port"]
            if port not in seen_ports or (p["pid"] and not seen_ports[port]["pid"]):
                seen_ports[port] = p
        return sorted(list(seen_ports.values()), key=lambda x: x["port"])
    except Exception:
        return []


def build_environment_summaries(relevance: str = "auto") -> dict:
    """
    Build environment awareness data from awakened state.
    Returns a dictionary suitable for templates.

    Args:
        relevance: "android", "macos", "both", or "auto"
    """
    try:
        from app.core.environment import get_awakened_state
        state = get_awakened_state()
        if not state:
            return {}

        data = {
            "macos": None,
            "android_devices": [],
            "network": None
        }

        # 1. Host (macOS) Info
        if state.host:
            host_info = {
                "os_name": state.host.os_name,
                "model": state.host.model,
                "cpu": state.host.cpu,
                "os_version": state.host.os_version,
                "top_apps": []
            }
            if relevance in ["macos", "both", "auto"]:
                if state.host.installed_apps:
                    if state.host.app_usage_stats:
                        host_info["top_apps"] = [s.app_name for s in state.host.app_usage_stats]
                    else:
                        host_info["top_apps"] = sorted(state.host.installed_apps)
            # Linux specific details
            if state.host.os_name == "Linux":
                host_info["distro"] = getattr(state.host, "distro", "Linux")
                host_info["sudo_available"] = getattr(state.host, "sudo_available", False)
                host_info["disk_space"] = getattr(state.host, "disk_space", None)
                host_info["systemd_services"] = getattr(state.host, "systemd_services", [])
                host_info["gpus"] = getattr(state.host, "gpus", [])

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
                        "more_count": 0
                    }
                    if dev.installed_packages:
                        dev_data["top_pkgs"] = dev.installed_packages
                        dev_data["more_count"] = len(dev.installed_packages)
                    data["android_devices"].append(dev_data)

        # 3. Network
        if state.network:
            data["network"] = {
                "internet_connected": state.network.internet_connected
            }

        # 4. Background Services and Listening Ports
        data["running_services"] = _get_active_background_tasks()
        data["active_ports"] = _get_listening_local_ports()
        data["docker_containers"] = getattr(state, "docker_containers", [])

        return data

    except Exception:
        return {}


def build_environment_prompt(relevance: str = "auto") -> str:
    """Legacy wrapper for build_environment_summaries."""
    summaries = build_environment_summaries(relevance=relevance)

    # Add capability boundaries for the legacy prompt
    boundaries = get_capability_boundaries()
    if boundaries:
        summaries.append("Limitations:")
        for boundary in boundaries[:5]:
            summaries.append(f"  - {boundary}")

    return "\n".join([f"- {s}" if not s.startswith(" ") else s for s in summaries])


def get_capability_boundaries() -> list[str]:
    """
    Get all capability boundaries including dynamically learned ones.

    Returns combined static and dynamic boundaries from the boundary manager.
    """
    try:
        from app.core.environment.boundaries import boundary_manager
        return boundary_manager.get_all_boundaries()
    except Exception:
        # Fallback to state boundaries if manager unavailable
        try:
            from app.core.environment import get_awakened_state
            state = get_awakened_state()
            return state.capability_boundaries if state else []
        except Exception:
            return []


def _get_browser_status() -> dict | None:
    """Helper to safely retrieve browser status for prompt injection."""
    try:
        return browser_manager.get_status()
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"Failed to get browser status: {e}")
        return None
