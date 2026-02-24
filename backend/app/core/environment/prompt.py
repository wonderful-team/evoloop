"""
App Environment Prompt

Centralizes the logic for generating the "Awakening" section of the system prompt.
This ensures both the Supervisor and Skills share the same understanding of the environment.
"""
import logging
import os
from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import BaseMessage

from app.core.context.manager import ContextManager
from app.core.context.plugins import plugin_registry

logger = logging.getLogger(__name__)


class AppEnvironmentPrompt:
    """
    Generates the environment context string based on the current AwakenedState.
    """

    @staticmethod
    def build(messages: list[dict] = None) -> str:
        """
        Build the environment context string using Jinja2 fragments.
        """
        try:
            ctx = ContextManager.current()
            plugin_registry.hydrate_context(ctx)

            template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "engine", "prompts", "templates")
            env = Environment(loader=FileSystemLoader(template_dir))

            template_vars = {
                "environment": {
                    "summaries": ctx.environment_summaries,
                    "boundaries": ctx.active_boundaries,
                    "memory_replay": ctx.memory_replay,
                    "spatial_awareness": ctx.spatial_awareness,
                    "user_preferences": ctx.metadata.get("user_preferences", {}),
                    "system_rules": ctx.metadata.get("system_rules", []),
                },
                "tips": True
            }

            template = env.get_template("awakening.prompt.j2")
            return template.render(**template_vars)

        except Exception as e:
            logger.error(f"Failed to build AppEnvironmentPrompt via Jinja2: {e}")
            return ""


# Environment Prompt Utilities - Shared logic for building environment awareness sections.

def build_environment_summaries(relevance: str = "auto") -> list[str]:
    """
    Build environment awareness summaries from awakened state.
    Returns a list of strings suitable for EvoContext.environment_summaries.

    Args:
        relevance: "android", "macos", "both", or "auto"
    """
    try:
        from app.core.environment import get_awakened_state
        state = get_awakened_state()
        if not state:
            return ["Environment: Not yet awakened (using default settings)"]

        summaries = []

        # 1. Host (macOS) Info
        if state.macos:
            if relevance in ["macos", "both", "auto"]:
                summaries.append(f"Host: {state.macos.model} ({state.macos.cpu}), macOS {state.macos.os_version}")
                summaries.append("💡 Use `list_app_atlas()` to see apps with structural UI maps.")
            else:
                summaries.append("Host: Apple Silicon Mac (MacOS Environment Available)")

        # 2. Android Info
        if state.android_devices:
            if relevance in ["android", "both", "auto"]:
                for dev in state.android_devices:
                    emoji = "✅" if dev.is_reachable else "⚠️"
                    dev_info = f"Android Device {emoji} `{dev.device_id}`: {dev.model} (Android {dev.os_version}), Battery: {dev.battery_percent}%"

                    # Add Apps info only if mobile is highly relevant
                    if dev.installed_packages and (relevance in ["android", "both"]):
                        top_apps = ", ".join(dev.installed_packages[:5])
                        more_count = max(0, len(dev.installed_packages) - 5)
                        app_str = f" [Apps: {top_apps}"
                        if more_count > 0:
                            app_str += f", and {more_count} more"
                        app_str += "]"
                        dev_info += app_str

                    summaries.append(dev_info)
            else:
                dev_count = len(state.android_devices)
                summaries.append(f"Mobile: {dev_count} Android device(s) connected (ADB Available)")
        else:
            if relevance in ["android", "both", "auto"]:
                summaries.append("Connected Android Devices: None (mobile_control will fail)")

        # 3. Network
        if state.network:
            net_status = "Online" if state.network.internet_connected else "Offline"
            summaries.append(f"Network: {net_status}")

        return summaries

    except Exception:
        return ["Environment: Unable to retrieve (using default settings)"]


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


def detect_platform_relevance(messages: list) -> str:
    """
    Analyze message history to determine if the task is platform-specific.
    Returns: "android", "macos", "both", or "auto"
    """
    history_text = ""
    # Look at last 5 messages for context
    # messages can be langchain BaseMessage list

    for msg in messages[-5:]:
        content = ""
        if isinstance(msg, BaseMessage):
            content = msg.content
        elif isinstance(msg, dict):
            content = msg.get("content", "")

        if isinstance(content, str):
            history_text += f" {content.lower()}"

    has_android = any(k in history_text for k in ["android", "adb", "mobile", "phone", "mirror", "scrcpy", "tap", "swipe"])
    has_macos = any(k in history_text for k in ["mac", "desktop", "macos", "apple", "click", "type", "screenshot", "terminal"])

    if has_android and not has_macos:
        return "android"
    if has_macos and not has_android:
        return "macos"
    if has_android and has_macos:
        return "both"
    return "auto"  # Balanced summary
