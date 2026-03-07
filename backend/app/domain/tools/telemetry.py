import logging
from typing import Any

from app.core.environment import get_awakened_state
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(is_pollable=True)
async def get_environment_telemetry() -> dict[str, Any]:
    """
    Retrieves raw telemetry data about the current environment, including connected devices,
    installed applications, and system status.
    
    Use this tool at the start of a session or when you need to verify the state of 
    connected hardware (e.g., checking if an Android device is reachable or what 
    apps are available on MacOS).
    
    Returns a structured dictionary:
    - android_devices: List of models and their reachability.
    - macos: System info and top 10 most used apps.
    - network: Internet connectivity status.
    """
    state = get_awakened_state()
    if not state:
        return {"status": "error", "message": "Environment state not initialized."}

    telemetry = {
        "android_devices": [],
        "macos": None,
        "network": {
            "internet_connected": getattr(state.network, "internet_connected", False) if state.network else False
        }
    }

    # 1. Android Telemetry
    for dev in state.android_devices:
        telemetry["android_devices"].append({
            "device_id": dev.device_id,
            "model": dev.model,
            "os_version": dev.os_version,
            "is_reachable": dev.is_reachable,
            "battery": f"{dev.battery_percent}%"
        })

    # 2. MacOS Telemetry
    if state.macos:
        telemetry["macos"] = {
            "model": state.macos.model,
            "os_version": state.macos.os_version,
            "cpu": state.macos.cpu,
            "top_apps": [s.app_name for s in state.macos.app_usage_stats[:10]] if state.macos.app_usage_stats else []
        }

    return telemetry
