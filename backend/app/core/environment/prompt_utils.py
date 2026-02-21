"""
Environment Prompt Utilities - Shared logic for building environment awareness sections.
"""

from app.core.environment import get_awakened_state


def build_environment_prompt(relevance: str = "auto") -> str:
    """
    Build environment awareness section from awakened state.
    
    Args:
        relevance: "android", "macos", "both", or "auto"
    """
    try:
        state = get_awakened_state()
        
        if not state:
            return "- **Environment**: Not yet awakened (use default settings)"
        
        sections = []
        
        # 1. Host (macOS) Info
        if state.macos:
            if relevance in ["macos", "both", "auto"]:
                sections.append(f"- **Host**: {state.macos.model} ({state.macos.cpu}), macOS {state.macos.os_version}")
                
                # Bundle ID Awareness (On-demand)
                sections.append("  💡 Use `list_app_atlas()` to see all applications with structural UI maps available.")
            else:
                sections.append("- **Host**: Apple Silicon Mac (MacOS Environment Available)")
        
        # 2. Android Info
        if state.android_devices:
            if relevance in ["android", "both", "auto"]:
                sections.append("- **Connected Android Devices**:")
                for dev in state.android_devices:
                    emoji = "✅" if dev.is_reachable else "⚠️"
                    dev_info = f"  - {emoji} `{dev.device_id}`: {dev.model} (Android {dev.os_version}), Battery: {dev.battery_percent}%"
                    
                    # Add Apps info only if mobile is highly relevant
                    if dev.installed_packages and (relevance in ["android", "both"]):
                        top_apps = ", ".join(dev.installed_packages[:5])
                        more_count = max(0, len(dev.installed_packages) - 5)
                        app_str = f" [Apps: {top_apps}"
                        if more_count > 0:
                            app_str += f", and {more_count} more"
                        app_str += "]"
                        dev_info += app_str
                    
                    sections.append(dev_info)
            else:
                # Summary version when not directly relevant
                dev_count = len(state.android_devices)
                sections.append(f"- **Mobile**: {dev_count} Android device(s) connected (ADB Available)")
        else:
            if relevance in ["android", "both", "auto"]:
                sections.append("- **Connected Android Devices**: None (mobile_control will fail)")
        
        # 3. Network
        if state.network:
            net_status = "Online" if state.network.internet_connected else "Offline"
            sections.append(f"- **Network**: {net_status}")
        
        # 4. Capability Boundaries (static + dynamic)
        boundaries = get_capability_boundaries()
        if boundaries:
            sections.append("- **Limitations**:")
            for boundary in boundaries[:5]:  # Limit to avoid prompt bloat
                sections.append(f"  - {boundary}")
            if len(boundaries) > 5:
                sections.append(f"  - ...and {len(boundaries) - 5} more constraints")
        
        return "\n".join(sections)
        
    except Exception:
        return "- **Environment**: Unable to retrieve (use default settings)"


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
    from langchain_core.messages import BaseMessage
    
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
    
    if has_android and not has_macos: return "android"
    if has_macos and not has_android: return "macos"
    if has_android and has_macos: return "both"
    return "auto" # Balanced summary
